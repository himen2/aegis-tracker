"""
Aegis — сбор и агрегация метрик.
Поддерживает: скользящее среднее, экспоненциальное сглаживание,
              автоматический шаг, сводная статистика.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
import math


# Метрики, для которых меньшее значение = лучше (эвристика auto)
_MIN_PATTERNS = frozenset([
    'loss', 'error', 'err', 'mae', 'mse', 'rmse', 'mape', 'wer', 'cer',
    'perplexity', 'ppl', 'nll', 'divergence', 'dist', 'distance',
    'penalty', 'cost', 'diff', 'gap', 'latency', 'fid', 'bce', 'kl',
])


def _auto_direction(name: str) -> str:
    """Определяет направление best по имени метрики (эвристика)."""
    part = name.lower().rsplit('/', 1)[-1]  # "train/loss" → "loss"
    return "min" if any(p in part for p in _MIN_PATTERNS) else "max"


@dataclass
class MetricDefinition:
    """Определяет поведение метрики при трекинге."""
    direction: str = "auto"             # "min" | "max" | "auto"
    step_metric: Optional[str] = None  # кастомная ось X (для будущих графиков)
    summary: str = "last"              # "last" | "best" | "mean"


class MetricSeries:
    """Один временной ряд метрики с агрегацией."""

    def __init__(self, name: str, smoothing: float = 0.0, direction: str = "auto"):
        self.name = name
        self.smoothing = smoothing
        self._direction = direction
        self._steps: List[int] = []
        self._values: List[float] = []
        self._smoothed: List[float] = []
        self._ema: Optional[float] = None
        self._step_to_value: Dict[int, float] = {}  # O(1) lookup для history_for_api

    def add(self, value: float, step: int):
        if not isinstance(value, (int, float)) or math.isnan(value):
            return
        fv = float(value)
        self._steps.append(step)
        self._values.append(fv)
        self._step_to_value[step] = fv
        if self.smoothing > 0:
            if self._ema is None:
                self._ema = float(value)
            else:
                self._ema = self.smoothing * self._ema + (1 - self.smoothing) * value
            self._smoothed.append(self._ema)
        else:
            self._smoothed.append(float(value))

    @property
    def steps(self) -> List[int]:
        return self._steps

    @property
    def values(self) -> List[float]:
        return self._values

    @property
    def smoothed(self) -> List[float]:
        return self._smoothed

    @property
    def last(self) -> Optional[float]:
        return self._values[-1] if self._values else None

    @property
    def best(self) -> Optional[float]:
        if not self._values:
            return None
        direction = self._direction if self._direction != "auto" else _auto_direction(self.name)
        return min(self._values) if direction == "min" else max(self._values)

    @property
    def mean(self) -> Optional[float]:
        if not self._values:
            return None
        return sum(self._values) / len(self._values)

    @property
    def std(self) -> Optional[float]:
        if len(self._values) < 2:
            return None
        m = self.mean
        return math.sqrt(sum((v - m) ** 2 for v in self._values) / len(self._values))

    def summary(self) -> Dict[str, Any]:
        return {
            "last": self.last,
            "best": self.best,
            "mean": round(self.mean, 6) if self.mean is not None else None,
            "std": round(self.std, 6) if self.std is not None else None,
            "count": len(self._values),
        }


class MetricCollector:
    def __init__(self, smoothing: float = 0.0):
        self._series: Dict[str, MetricSeries] = {}
        self._definitions: Dict[str, MetricDefinition] = {}
        self._step: int = 0
        self._smoothing = smoothing
        self._batch: List[dict] = []

    @property
    def step(self) -> int:
        return self._step

    def log(self, metrics: Dict[str, Any], step: Optional[int] = None) -> int:
        if step is not None:
            self._step = step
        else:
            self._step += 1
        current_step = self._step
        logged: Dict[str, float] = {}
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                if key not in self._series:
                    defn = self._definitions.get(key)
                    direction = defn.direction if defn else "auto"
                    self._series[key] = MetricSeries(key, self._smoothing, direction=direction)
                self._series[key].add(float(value), current_step)
                logged[key] = float(value)
        if logged:
            self._batch.append({"step": current_step, "metrics": logged})
        return current_step

    def flush_batch(self) -> List[dict]:
        batch = list(self._batch)
        self._batch.clear()
        return batch

    def define_metric(
        self,
        name: str,
        direction: str = "auto",
        step_metric: Optional[str] = None,
        summary: str = "last",
    ) -> None:
        """Настраивает поведение метрики при трекинге."""
        self._definitions[name] = MetricDefinition(
            direction=direction, step_metric=step_metric, summary=summary,
        )
        # Обновляем уже созданный ряд, если он существует
        if name in self._series:
            self._series[name]._direction = direction

    def get_series(self, name: str):
        return self._series.get(name)

    def all_series(self) -> Dict[str, MetricSeries]:
        return dict(self._series)

    @property
    def metric_names(self) -> List[str]:
        return list(self._series.keys())

    def summary(self) -> Dict[str, Any]:
        result = {}
        for name, series in self._series.items():
            defn = self._definitions.get(name)
            summary_type = defn.summary if defn else "last"
            if summary_type == "best":
                result[name] = series.best
            elif summary_type == "mean":
                result[name] = series.mean
            else:
                result[name] = series.last
        return result

    def full_summary(self) -> Dict[str, Any]:
        return {name: series.summary() for name, series in self._series.items()}

    def history_for_api(self) -> List[dict]:
        if not self._series:
            return []
        all_steps = sorted({
            s for series in self._series.values() for s in series.steps
        })
        result = []
        for step in all_steps:
            point: Dict[str, Any] = {"step": step}
            for name, series in self._series.items():
                val = series._step_to_value.get(step)
                if val is not None:
                    point[name] = val
            result.append(point)
        return result

