"""
Aegis — точный таймер для измерения времени обучения.
"""
import time
from typing import Optional


class AegisTimer:
    def __init__(self):
        self._start: Optional[float] = None
        self._pause_start: Optional[float] = None
        self._paused_total: float = 0.0
        self._running = False

    def start(self) -> "AegisTimer":
        self._start = time.perf_counter()
        self._paused_total = 0.0
        self._running = True
        return self

    def pause(self):
        if self._running and self._pause_start is None:
            self._pause_start = time.perf_counter()

    def resume(self):
        if self._pause_start is not None:
            self._paused_total += time.perf_counter() - self._pause_start
            self._pause_start = None

    def elapsed(self) -> float:
        if self._start is None:
            return 0.0
        now = time.perf_counter()
        paused = self._paused_total
        if self._pause_start is not None:
            paused += now - self._pause_start
        return now - self._start - paused

    def elapsed_str(self) -> str:
        secs = int(self.elapsed())
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}h {m:02d}m {s:02d}s"
        elif m:
            return f"{m}m {s:02d}s"
        else:
            return f"{s}s"

    def stop(self) -> float:
        elapsed = self.elapsed()
        self._running = False
        return elapsed

    @staticmethod
    def now_ms() -> int:
        return int(time.time() * 1000)

    @staticmethod
    def now_iso() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

