"""
Aegis — главный класс запуска AegisRun.
Центральный объект, который пользователь получает через aegis.init().
"""
import threading
import signal
from typing import Dict, Any, Optional, List

from .config import AegisConfig
from ..utils.uid import generate_run_id, config_fingerprint
from ..utils.env import detect_environment, get_platform_info, get_backend_url, get_dashboard_url, get_api_token
from ..utils.timer import AegisTimer
from ..utils.ddp import is_main_process, is_distributed, get_ddp_info
from ..metrics.collector import MetricCollector
from ..metrics.system import SystemProbe
from ..metrics.alerts import AlertManager, AlertRule
from ..storage.local_db import LocalStore
from ..storage.artifacts import ArtifactManager
from ..transport.sender import SmartSender, AegisHTTP
from ..display.renderer import JupyterRenderer, TerminalRenderer

_PRINT_LOCK = threading.Lock()


def _safe_print(msg: str):
    with _PRINT_LOCK:
        try:
            print(msg)
        except Exception:
            pass


class AegisRun:
    """
    Объект запуска эксперимента.
    
    Создаётся через aegis.init(), поддерживает context manager:
    
        with aegis.init(project="cv", config={"lr": 1e-3}) as run:
            for epoch in range(50):
                run.log({"loss": 0.5, "acc": 0.9})
    
    Или явно:
        run = aegis.init(project="nlp")
        run.log({"loss": 0.4})
        run.finish()
    """

    def __init__(
        self,
        project: str,
        name: Optional[str] = None,
        config: Optional[dict] = None,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
        base_url: Optional[str] = None,
        api_token: Optional[str] = None,
        smoothing: float = 0.0,
        log_system: bool = True,
        display_interval: int = 1,
        db_path: Optional[str] = None,
        ddp_aware: bool = True,
    ):
        self.project = project
        self.id = generate_run_id()
        self.name = name or f"run-{self.id[:8]}"
        self.tags: List[str] = list(tags or [])
        self.notes: str = notes or ""
        self.base_url = (base_url or get_backend_url()).rstrip('/')
        self.dashboard_url = get_dashboard_url()
        self.api_token = (api_token if api_token is not None else get_api_token()).strip()
        self.config = AegisConfig(config or {})
        self._fingerprint = config_fingerprint(self.config.to_dict())
        self._env = detect_environment()
        self._is_notebook: bool = self._env in ('jupyter', 'colab')

        # ── DDP: пропускаем логирование на не-главных процессах ──
        self._ddp_aware = ddp_aware
        self._is_main = is_main_process() if ddp_aware else True
        self._ddp_info = get_ddp_info() if ddp_aware and is_distributed() else None

        # Если DDP и не главный процесс — тихий режим
        if not self._is_main:
            self._noop = True
        else:
            self._noop = False

        self._timer = AegisTimer()
        self._collector = MetricCollector(smoothing=smoothing)
        self._db = LocalStore(db_path)
        self._http = AegisHTTP(self.base_url, api_token=self.api_token)
        self._sender = SmartSender(self._http, self.id, self._db)

        self._jupyter_renderer = JupyterRenderer(smoothing=smoothing > 0)
        self._terminal_renderer = TerminalRenderer()
        self._display_interval = display_interval
        self._display_counter = 0

        self._system_probe = SystemProbe(interval=15.0) if log_system else None
        self._finished = False
        self._status = "running"

        # ── Алерты ──
        self._alert_manager = AlertManager()

        # ── Артефакты ──
        self._artifact_manager = ArtifactManager(self.id, self.project)

        if self._noop:
            return  # DDP non-main: не инициализируем сеть и потоки

        self._timer.start()
        self._init_run()
        self._sender.start()
        if self._system_probe:
            self._system_probe.start()

        try:
            self._orig_sigint = signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGINT, self._handle_interrupt)
        except (ValueError, OSError):
            self._orig_sigint = None  # не main-поток или платформа без SIGINT

    def _init_run(self):
        platform = get_platform_info()
        # Добавляем DDP-информацию в platform
        if self._ddp_info:
            platform["ddp"] = self._ddp_info
        self._db.ensure_project(self.project)
        self._db.create_run(
            self.id, self.project, self.name,
            self.config.to_dict(), self._fingerprint, platform,
            tags=self.tags, notes=self.notes,
        )

        result = self._http.post("/api/aegis/run", {
            "project_name": self.project,
            "run_name": self.name,
            "config": self.config.to_dict(),
            "run_id": self.id,
            "tags": self.tags,
            "notes": self.notes,
        })

        connected = result is not None
        self._sender._connected = connected

        status = "подключён" if connected else "офлайн"
        ddp_line = ""
        if self._ddp_info:
            ddp_line = (f"\n         DDP: rank={self._ddp_info['rank']} "
                       f"world_size={self._ddp_info['world_size']}")
        tags_line = f"\n         tags={self.tags}" if self.tags else ""
        _safe_print(
            f"\n\033[1m\033[91m[AEGIS]\033[0m  run={self.name}  "
            f"project={self.project}  id={self.id}\n"
            f"         fingerprint={self._fingerprint}  env={self._env}  режим={status}"
            f"{ddp_line}{tags_line}\n"
            f"         backend: {self.base_url}\n"
            f"         дашборд: {self.dashboard_url}/project/{self.project}\n"
        )

    def log(self, metrics: Dict[str, Any] = None, step: Optional[int] = None, **kwargs):
        if self._noop:
            return  # DDP non-main: молча пропускаем
        if metrics is None:
            metrics = {}
        if kwargs:
            metrics = {**metrics, **kwargs}

        if self._finished:
            _safe_print("[Aegis] Предупреждение: run уже завершён, log() проигнорирован")
            return

        if self._system_probe:
            sys_metrics = self._system_probe.get_latest()
            # Если фоновый поток ещё не снял первый снимок — берём синхронно
            if not sys_metrics:
                sys_metrics = self._system_probe.snapshot()
            metrics = {**metrics, **sys_metrics}

        current_step = self._collector.log(metrics, step=step)

        # ── Проверка алертов ──
        self._alert_manager.check_metrics(metrics, current_step)

        batch = self._collector.flush_batch()
        if batch:
            db_ids = self._db.save_metric_batch(self.id, batch)
            for item, db_id in zip(batch, db_ids):
                item['_db_id'] = db_id
                self._sender.enqueue(item)

        self._display_counter += 1
        if self._display_counter % self._display_interval == 0:
            self._render()

    def log_batch(self, metrics_list: List[Dict[str, Any]], start_step: int = 1):
        for i, m in enumerate(metrics_list):
            self.log(m, step=start_step + i)

    def summary(self) -> Dict[str, Any]:
        return self._collector.summary()

    def full_summary(self) -> Dict[str, Any]:
        return self._collector.full_summary()

    def define_metric(
        self,
        name: str,
        direction: str = "auto",
        step_metric: str = None,
        summary: str = "last",
    ) -> None:
        """Настраивает поведение метрики.

        Args:
            name:        Имя метрики.
            direction:   "min" | "max" | "auto" — что считать лучшим значением.
            step_metric: Имя метрики для оси X (по умолчанию — глобальный step).
            summary:     "last" | "best" | "mean" — что фиксировать в итоговом summary.

        Пример::

            run.define_metric("val_loss", direction="min")
            run.define_metric("f1", direction="max", summary="best")
            run.define_metric("perplexity", direction="min", summary="best")
        """
        self._collector.define_metric(
            name, direction=direction, step_metric=step_metric, summary=summary,
        )

    @property
    def step(self) -> int:
        return self._collector.step

    @property
    def elapsed(self) -> str:
        return self._timer.elapsed_str()

    @property
    def is_connected(self) -> bool:
        return self._sender.is_connected

    def keras_callback(self):
        from ..hooks.frameworks import make_keras_callback_class
        return make_keras_callback_class(self)

    def pytorch_hook(self, model=None):
        from ..hooks.frameworks import AegisPyTorchHook
        return AegisPyTorchHook(self, model)

    def wrap_sklearn(self, model):
        from ..hooks.frameworks import AegisSklearnWrapper
        return AegisSklearnWrapper(self, model)

    def add_tags(self, tags: List[str]) -> None:
        """Добавляет теги к запуску (можно вызывать в процессе обучения)."""
        for tag in tags:
            if tag not in self.tags:
                self.tags.append(tag)
        self._db.update_run_tags(self.id, self.tags)

    def set_notes(self, notes: str) -> None:
        """Обновляет текстовое примечание к запуску."""
        self.notes = notes
        self._db.update_run_notes(self.id, notes)

    # ── Алерты ───────────────────────────────────────

    def alert_on_nan(self, metric: str = "*", callback=None):
        """Срабатывает, если метрика становится NaN.

        Пример::

            run.alert_on_nan()  # все метрики
            run.alert_on_nan("loss")  # только loss
        """
        self._alert_manager.alert_on_nan(metric, callback=callback)

    def alert_on_inf(self, metric: str = "*", callback=None):
        """Срабатывает, если метрика становится Infinity."""
        self._alert_manager.alert_on_inf(metric, callback=callback)

    def alert_above(self, metric: str, threshold: float, patience: int = 1, callback=None):
        """Срабатывает, если метрика превышает порог patience раз подряд.

        Пример::

            run.alert_above("loss", threshold=10.0, patience=3)
        """
        self._alert_manager.alert_above(metric, threshold, patience, callback)

    def alert_below(self, metric: str, threshold: float, patience: int = 1, callback=None):
        """Срабатывает, если метрика падает ниже порога."""
        self._alert_manager.alert_below(metric, threshold, patience, callback)

    @property
    def alerts(self):
        """Список сработавших алертов."""
        return self._alert_manager.triggered_alerts

    # ── Артефакты ────────────────────────────────────

    def log_artifact(self, path: str, type: str = "file", name: str = None, metadata: dict = None):
        """Сохраняет файл как артефакт запуска.

        Пример::

            run.log_artifact("best_model.pth", type="model")
            run.log_artifact("config.yaml", type="config")
            run.log_artifact("predictions.csv", type="output")
        """
        return self._artifact_manager.log_artifact(path, type=type, name=name, metadata=metadata)

    def log_directory(self, dir_path: str, type: str = "output", name: str = None, extensions: list = None):
        """Сохраняет все файлы из директории."""
        return self._artifact_manager.log_directory(dir_path, type=type, name=name, extensions=extensions)

    @property
    def artifacts(self):
        """Список сохранённых артефактов."""
        return self._artifact_manager.artifacts

    def finish(self, exit_code: int = 0):
        if self._finished:
            return
        self._finished = True
        self._status = "finished" if exit_code == 0 else "failed"

        if self._system_probe:
            self._system_probe.stop()
        self._sender.stop()

        summary = self._collector.summary()
        self._db.finish_run(self.id, summary)

        self._http.post(f"/api/aegis/run/{self.id}/finish", {
            "status": self._status,
            "summary": summary,
        })

        try:
            if self._orig_sigint is not None:
                signal.signal(signal.SIGINT, self._orig_sigint)
        except (ValueError, OSError):
            pass
        self._db.close()  # освобождаем соединение с локальной БД

        _safe_print(
            f"\n\033[1m\033[91m[AEGIS]\033[0m  {self._status} — {self.name}\n"
            f"         время: {self._timer.elapsed_str()}  шагов: {self._collector.step}\n"
            f"         итог:  " +
            "  ".join(f"{k}={v:.4f}" for k, v in summary.items() if isinstance(v, float)) +
            "\n"
        )

    def __enter__(self) -> "AegisRun":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        code = 1 if exc_type is not None else 0
        self.finish(exit_code=code)
        return False

    def _render(self):
        elapsed = self._timer.elapsed_str()
        connected = self._sender.is_connected
        if self._is_notebook:
            self._jupyter_renderer.render(self._collector, run_name=self.name)
        else:
            self._terminal_renderer.render(
                self._collector,
                run_name=self.name,
                elapsed=elapsed,
                connected=connected,
            )

    def _handle_interrupt(self, signum, frame):
        _safe_print("\n[Aegis] Прерывание SIGINT, завершаем run...")
        self.finish(exit_code=1)
        if callable(self._orig_sigint):
            self._orig_sigint(signum, frame)

