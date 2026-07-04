"""
Aegis — Алерты: автоматическая проверка метрик на аномалии.
Поддерживает: NaN/Inf детектирование, пороговые значения, коллбеки.
"""
import math
import threading
from typing import Callable, Dict, Any, List, Optional


class AlertRule:
    """Одно правило проверки метрики."""

    def __init__(
        self,
        metric_name: str,
        condition: str = "nan",  # "nan" | "inf" | "above" | "below" | "plateau"
        threshold: Optional[float] = None,
        patience: int = 1,  # сколько раз подряд нарушить, прежде чем сработает
        callback: Optional[Callable[[str, float, int], None]] = None,
        message: Optional[str] = None,
    ):
        self.metric_name = metric_name
        self.condition = condition
        self.threshold = threshold
        self.patience = patience
        self.callback = callback
        self.message = message
        self._violations = 0
        self._triggered = False
        self._last_value: Optional[float] = None
        self._plateau_count = 0

    def check(self, value: float, step: int) -> Optional[str]:
        """Проверяет значение. Возвращает сообщение об алерте или None."""
        if self._triggered:
            return None

        violated = False

        if self.condition == "nan":
            violated = (not isinstance(value, (int, float))) or math.isnan(value)
        elif self.condition == "inf":
            violated = isinstance(value, float) and math.isinf(value)
        elif self.condition == "above" and self.threshold is not None:
            violated = isinstance(value, (int, float)) and value > self.threshold
        elif self.condition == "below" and self.threshold is not None:
            violated = isinstance(value, (int, float)) and value < self.threshold
        elif self.condition == "plateau":
            if self._last_value is not None and isinstance(value, (int, float)):
                if abs(value - self._last_value) < 1e-8:
                    self._plateau_count += 1
                else:
                    self._plateau_count = 0
                violated = self._plateau_count >= self.patience
            self._last_value = value
            if not violated:
                return None

        if violated:
            self._violations += 1
        else:
            self._violations = 0

        if self._violations >= self.patience:
            self._triggered = True
            msg = self.message or (
                f"[Aegis Alert] {self.metric_name} = {value} "
                f"(condition: {self.condition}, step: {step})"
            )
            if self.callback:
                try:
                    self.callback(self.metric_name, value, step)
                except Exception:
                    pass
            return msg

        return None

    def reset(self):
        self._violations = 0
        self._triggered = False
        self._last_value = None
        self._plateau_count = 0


class AlertManager:
    """Менеджер алертов для AegisRun."""

    def __init__(self):
        self._rules: List[AlertRule] = []
        self._alerts: List[str] = []
        self._lock = threading.Lock()
        self._print_lock = threading.Lock()

    def add_rule(self, rule: AlertRule):
        with self._lock:
            self._rules.append(rule)

    def alert_on_nan(
        self,
        metric: str = "*",
        callback: Optional[Callable] = None,
    ):
        """Shortcut: срабатывает, если метрика становится NaN."""
        self.add_rule(AlertRule(
            metric_name=metric,
            condition="nan",
            patience=1,
            callback=callback,
            message=f"[Aegis ALERT] Метрика '{metric}' стала NaN!",
        ))

    def alert_on_inf(
        self,
        metric: str = "*",
        callback: Optional[Callable] = None,
    ):
        """Shortcut: срабатывает, если метрика становится Infinity."""
        self.add_rule(AlertRule(
            metric_name=metric,
            condition="inf",
            patience=1,
            callback=callback,
            message=f"[Aegis ALERT] Метрика '{metric}' стала Infinity!",
        ))

    def alert_above(
        self,
        metric: str,
        threshold: float,
        patience: int = 1,
        callback: Optional[Callable] = None,
    ):
        """Срабатывает, если метрика превышает порог patience раз подряд."""
        self.add_rule(AlertRule(
            metric_name=metric,
            condition="above",
            threshold=threshold,
            patience=patience,
            callback=callback,
        ))

    def alert_below(
        self,
        metric: str,
        threshold: float,
        patience: int = 1,
        callback: Optional[Callable] = None,
    ):
        """Срабатывает, если метрика падает ниже порога patience раз подряд."""
        self.add_rule(AlertRule(
            metric_name=metric,
            condition="below",
            threshold=threshold,
            patience=patience,
            callback=callback,
        ))

    def check_metrics(self, metrics: Dict[str, Any], step: int) -> List[str]:
        """Проверяет все метрики по всем правилам. Возвращает список сработавших алертов."""
        fired: List[str] = []
        with self._lock:
            for rule in self._rules:
                # Wildcard: проверяем все метрики
                if rule.metric_name == "*":
                    for name, value in metrics.items():
                        if isinstance(value, (int, float)):
                            msg = rule.check(value, step)
                            if msg:
                                real_msg = msg.replace("'*'", f"'{name}'")
                                fired.append(real_msg)
                                self._alerts.append(real_msg)
                else:
                    value = metrics.get(rule.metric_name)
                    if value is not None:
                        msg = rule.check(value, step)
                        if msg:
                            fired.append(msg)
                            self._alerts.append(msg)

        # Печатаем алерты в консоль
        for msg in fired:
            with self._print_lock:
                try:
                    print(f"\033[1m\033[91m{msg}\033[0m")
                except Exception:
                    pass

        return fired

    @property
    def triggered_alerts(self) -> List[str]:
        with self._lock:
            return list(self._alerts)

    def reset(self):
        with self._lock:
            for rule in self._rules:
                rule.reset()
            self._alerts.clear()
