"""
Aegis — асинхронный транспорт.
SmartSender: фоновая очередь с батчингом, retry и heartbeat.
"""
import threading
import queue
import time
import json
import urllib.request
import urllib.error
import urllib.parse
from typing import List, Dict, Any, Optional


class AegisHTTP:
    """
    Лёгкий HTTP-клиент без внешних зависимостей (только stdlib).
    Используется вместо requests для минимизации зависимостей.
    """

    def __init__(self, base_url: str, timeout: float = 5.0, api_token: str = "", extra_headers: Optional[dict] = None):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.api_token = api_token.strip()
        self.extra_headers = dict(extra_headers or {})

    def _headers(self) -> dict:
        headers = {'Content-Type': 'application/json', 'X-Aegis-Client': 'python-sdk'}
        if self.api_token:
            headers['X-API-Key'] = self.api_token
        headers.update(self.extra_headers)
        return headers

    def post(self, path: str, data: dict) -> Optional[dict]:
        url = f"{self.base_url}{path}"
        body = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(
            url, data=body,
            headers=self._headers(),
            method='POST'
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception:
            return None

    def get(self, path: str) -> Optional[dict]:
        url = f"{self.base_url}{path}"
        try:
            req = urllib.request.Request(url, headers=self._headers(), method='GET')
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception:
            return None

    def ping(self) -> bool:
        result = self.get("/health")
        return result is not None


class PySmartSender:
    """
    Фоновый поток для отправки метрик на сервер (Чистый Python).
    """

    BATCH_SIZE = 50
    BATCH_INTERVAL = 1.0     # секунды между отправками
    HEARTBEAT_INTERVAL = 10  # секунды между пингами
    MAX_RETRY = 3
    RETRY_DELAY = 2.0

    def __init__(self, http: AegisHTTP, run_id: str, local_db=None):
        self._http = http
        self._run_id = run_id
        self._db = local_db
        self._queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._connected = False
        self._thread = threading.Thread(target=self._loop, daemon=True, name=f"aegis-sender-{run_id[:8]}")
        self._hb_thread = threading.Thread(target=self._heartbeat, daemon=True, name=f"aegis-hb-{run_id[:8]}")

    def start(self):
        self._thread.start()
        self._hb_thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=5)
        self._hb_thread.join(timeout=2)

    def enqueue(self, item: dict):
        """Добавляет точку метрики в очередь."""
        self._queue.put(item)

    def _loop(self):
        pending: List[dict] = []
        last_flush = time.monotonic()

        while not self._stop.is_set() or not self._queue.empty():
            deadline = last_flush + self.BATCH_INTERVAL
            while time.monotonic() < deadline and len(pending) < self.BATCH_SIZE:
                try:
                    item = self._queue.get(timeout=0.1)
                    pending.append(item)
                    self._queue.task_done()
                except queue.Empty:
                    break

            if pending:
                success = self._send_batch(pending)
                if success:
                    if self._db:
                        ids = [p.get('_db_id') for p in pending if p.get('_db_id')]
                        if ids:
                            self._db.mark_synced(ids)
                    pending = []
                else:
                    time.sleep(self.RETRY_DELAY)

                last_flush = time.monotonic()

        if pending:
            self._send_batch(pending)

    def _send_batch(self, batch: List[dict]) -> bool:
        for attempt in range(self.MAX_RETRY):
            result = self._http.post(
                f"/api/aegis/run/{self._run_id}/log_batch",
                {"batch": [{"step": p["step"], "metrics": p["metrics"]} for p in batch]}
            )
            if result is not None:
                self._connected = True
                return True
            if attempt < self.MAX_RETRY - 1:
                time.sleep(self.RETRY_DELAY * (attempt + 1))

        self._connected = False
        return False

    def _heartbeat(self):
        was_connected = False
        while not self._stop.wait(self.HEARTBEAT_INTERVAL):
            now_connected = self._http.ping()
            if now_connected and not was_connected and self._db:
                self._resync_offline_metrics()
            self._connected = now_connected
            was_connected = now_connected

    def _resync_offline_metrics(self) -> None:
        """Досылает метрики с synced=0 при восстановлении связи с backend."""
        try:
            while True:
                batch = self._db.get_unsynced_metrics(self._run_id, limit=self.BATCH_SIZE)
                if not batch:
                    break
                result = self._http.post(
                    f"/api/aegis/run/{self._run_id}/log_batch",
                    {"batch": [{"step": p["step"], "metrics": p["metrics"]} for p in batch]}
                )
                if result is not None:
                    self._db.mark_synced([p["_id"] for p in batch])
                else:
                    break  # backend недоступен, попробуем при следующем heartbeat
        except Exception:
            pass  # не роняем heartbeat-поток

    @property
    def is_connected(self) -> bool:
        return self._connected

class RustSenderWrapper:
    """
    Обертка над высокопроизводительным Rust-ядром.
    """
    def __init__(self, http: AegisHTTP, run_id: str, local_db=None):
        import aegis_core
        self._http = http
        self._run_id = run_id
        self._db = local_db
        # RustSender(base_url, run_id, api_token)
        self._rust = aegis_core.RustSender(http.base_url, run_id, http.api_token)
        
        # Для heartbeat и offline resync мы оставим легкий python-поток,
        # так как RustSender занимается только горячей отправкой.
        self._stop = threading.Event()
        self._hb_thread = threading.Thread(target=self._heartbeat, daemon=True, name=f"aegis-rust-hb-{run_id[:8]}")
        self._connected = False

    def start(self):
        self._rust.start()
        self._hb_thread.start()

    def stop(self):
        self._stop.set()
        self._rust.stop()
        self._hb_thread.join(timeout=2)

    def enqueue(self, item: dict):
        self._rust.enqueue(json.dumps(item))
        # Оптимизация: мы помечаем как synced сразу в Python, чтобы БД не пухла,
        # так как RustSender гарантирует отправку или retry в памяти.
        if self._db and '_db_id' in item:
            self._db.mark_synced([item['_db_id']])

    def _heartbeat(self):
        was_connected = False
        while not self._stop.wait(10):
            now_connected = self._http.ping()
            if now_connected and not was_connected and self._db:
                # Попытка дослать оффлайн метрики
                pass 
            self._connected = now_connected
            was_connected = now_connected

    @property
    def is_connected(self) -> bool:
        return self._rust.is_connected()

def SmartSender(http: AegisHTTP, run_id: str, local_db=None):
    try:
        import aegis_core
        return RustSenderWrapper(http, run_id, local_db)
    except ImportError:
        return PySmartSender(http, run_id, local_db)
