"""
Aegis — локальное хранилище (SQLite).
OfflineFirst: все данные пишутся локально, сервер — зеркало.
"""
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _PersistentConn:
    """Прокси над sqlite3.Connection: close() — нет-оп, соединение живёт весь lifetime LocalStore."""
    __slots__ = ('_conn',)

    def __init__(self, conn: sqlite3.Connection) -> None:
        object.__setattr__(self, '_conn', conn)

    def __getattr__(self, name: str):
        return getattr(object.__getattribute__(self, '_conn'), name)

    def __setattr__(self, name: str, value) -> None:
        setattr(object.__getattribute__(self, '_conn'), name, value)

    def close(self) -> None:
        pass  # намеренно нет-оп: соединение переиспользуется между вызовами

    def real_close(self) -> None:
        """Фактически закрывает соединение (вызывается только при shutdown LocalStore)."""
        object.__getattribute__(self, '_conn').close()


class LocalStore:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            home = os.path.expanduser("~")
            aegis_dir = os.path.join(home, ".aegis")
            os.makedirs(aegis_dir, exist_ok=True)
            db_path = os.path.join(aegis_dir, "local.db")

        self._path = db_path
        self._lock = threading.Lock()
        self._conn: Optional[_PersistentConn] = None
        self._init_db()
        self._migrate_db()

    def close(self) -> None:
        """Явно закрывает соединение с БД. Вызывать при завершении работы."""
        with self._lock:
            if self._conn is not None:
                self._conn.real_close()
                self._conn = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def _connect(self) -> _PersistentConn:
        """Возвращает переиспользуемое соединение (WAL, NORMAL sync). Создаётся один раз."""
        if self._conn is None:
            raw = sqlite3.connect(self._path, check_same_thread=False)
            raw.row_factory = sqlite3.Row
            raw.execute("PRAGMA journal_mode=WAL")
            raw.execute("PRAGMA synchronous=NORMAL")
            self._conn = _PersistentConn(raw)
        return self._conn

    def _init_db(self):
        with self._lock:
            conn = self._connect()
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    id   INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS runs (
                    id          TEXT PRIMARY KEY,
                    project     TEXT NOT NULL,
                    name        TEXT NOT NULL,
                    status      TEXT NOT NULL DEFAULT 'running',
                    config      TEXT NOT NULL DEFAULT '{}',
                    summary     TEXT NOT NULL DEFAULT '{}',
                    fingerprint TEXT,
                    platform    TEXT NOT NULL DEFAULT '{}',
                    created_at  TEXT NOT NULL,
                    finished_at TEXT,
                    synced      INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS metrics (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id   TEXT NOT NULL,
                    step     INTEGER NOT NULL,
                    data     TEXT NOT NULL,
                    ts       TEXT NOT NULL,
                    synced   INTEGER NOT NULL DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_metrics_run ON metrics(run_id);
                CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project);
                CREATE INDEX IF NOT EXISTS idx_metrics_synced ON metrics(synced);
            """)
            conn.commit()
            conn.close()

    def _migrate_db(self):
        """Добавляет новые колонки в существующую БД (backward-compatible)."""
        with self._lock:
            conn = self._connect()
            try:
                existing = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
                if 'tags' not in existing:
                    conn.execute("ALTER TABLE runs ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'")
                if 'notes' not in existing:
                    conn.execute("ALTER TABLE runs ADD COLUMN notes TEXT NOT NULL DEFAULT ''")
                conn.commit()
            except Exception:
                pass
            finally:
                conn.close()

    def ensure_project(self, name: str):
        with self._lock:
            conn = self._connect()
            conn.execute(
                "INSERT OR IGNORE INTO projects (name, created_at) VALUES (?, ?)",
                (name, _now())
            )
            conn.commit()
            conn.close()

    def create_run(self, run_id: str, project: str, name: str,
                   config: dict, fingerprint: str = "", platform: dict = None,
                   tags: list = None, notes: str = "") -> dict:
        with self._lock:
            conn = self._connect()
            now = _now()
            conn.execute(
                """INSERT OR REPLACE INTO runs
                   (id, project, name, status, config, summary, fingerprint, platform, tags, notes, created_at)
                   VALUES (?, ?, ?, 'running', ?, '{}', ?, ?, ?, ?, ?)""",
                (run_id, project, name, json.dumps(config),
                 fingerprint, json.dumps(platform or {}),
                 json.dumps(tags or []), notes or "", now)
            )
            conn.commit()
            conn.close()
        return {"run_id": run_id, "run_name": name, "created_at": now}

    def update_run_tags(self, run_id: str, tags: list) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute("UPDATE runs SET tags=? WHERE id=?", (json.dumps(tags), run_id))
            conn.commit()
            conn.close()

    def update_run_notes(self, run_id: str, notes: str) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute("UPDATE runs SET notes=? WHERE id=?", (notes, run_id))
            conn.commit()
            conn.close()

    def finish_run(self, run_id: str, summary: dict):
        with self._lock:
            conn = self._connect()
            conn.execute(
                "UPDATE runs SET status='finished', summary=?, finished_at=? WHERE id=?",
                (json.dumps(summary), _now(), run_id)
            )
            conn.commit()
            conn.close()

    def fail_run(self, run_id: str, error: str = ""):
        with self._lock:
            conn = self._connect()
            conn.execute(
                "UPDATE runs SET status='failed', finished_at=? WHERE id=?",
                (_now(), run_id)
            )
            conn.commit()
            conn.close()

    def get_run(self, run_id: str) -> Optional[dict]:
        with self._lock:
            conn = self._connect()
            row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            conn.close()
            return dict(row) if row else None

    def list_runs(self, project: str) -> List[dict]:
        with self._lock:
            conn = self._connect()
            rows = conn.execute(
                "SELECT * FROM runs WHERE project=? ORDER BY created_at DESC", (project,)
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def save_metric_batch(self, run_id: str, batch: List[dict]) -> List[int]:
        """Сохраняет батч метрик. Возвращает список DB-ID вставленных строк."""
        if not batch:
            return []
        ids: List[int] = []
        now = _now()
        with self._lock:
            conn = self._connect()
            for item in batch:
                cursor = conn.execute(
                    "INSERT INTO metrics (run_id, step, data, ts, synced) VALUES (?, ?, ?, ?, 0)",
                    (run_id, item["step"], json.dumps(item["metrics"]), now)
                )
                ids.append(cursor.lastrowid)
            conn.commit()
            conn.close()
        return ids

    def get_unsynced_metrics(self, run_id: str, limit: int = 200) -> List[dict]:
        with self._lock:
            conn = self._connect()
            rows = conn.execute(
                "SELECT id, step, data FROM metrics WHERE run_id=? AND synced=0 LIMIT ?",
                (run_id, limit)
            ).fetchall()
            conn.close()
            return [{"_id": r["id"], "step": r["step"], "metrics": json.loads(r["data"])} for r in rows]

    def mark_synced(self, metric_ids: List[int]):
        if not metric_ids:
            return
        with self._lock:
            conn = self._connect()
            conn.execute(
                f"UPDATE metrics SET synced=1 WHERE id IN ({','.join('?' * len(metric_ids))})",
                metric_ids
            )
            conn.commit()
            conn.close()

    def get_all_metrics(self, run_id: str) -> List[dict]:
        with self._lock:
            conn = self._connect()
            rows = conn.execute(
                "SELECT step, data FROM metrics WHERE run_id=? ORDER BY step ASC",
                (run_id,)
            ).fetchall()
            conn.close()
        result = []
        for r in rows:
            point = {"step": r["step"]}
            point.update(json.loads(r["data"]))
            result.append(point)
        return result

