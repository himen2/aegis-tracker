"""
Aegis — хуки для фреймворков ML.
Автоматическое логирование без изменения кода обучения.
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.run import AegisRun


class AegisKerasCallback:
    """
    Callback для Keras / TensorFlow.
    """

    def __init__(self, run: "AegisRun"):
        try:
            import tensorflow as tf
            self._base = tf.keras.callbacks.Callback
        except ImportError:
            self._base = object

        self._run = run

    def on_epoch_end(self, epoch: int, logs: dict = None):
        if logs:
            self._run.log(dict(logs), step=epoch + 1)

    def on_train_batch_end(self, batch: int, logs: dict = None):
        pass

    def on_train_end(self, logs: dict = None):
        pass


def make_keras_callback_class(run: "AegisRun"):
    try:
        import tensorflow as tf
        Base = tf.keras.callbacks.Callback
    except ImportError:
        try:
            import keras  # type: ignore
            Base = keras.callbacks.Callback
        except ImportError:
            return AegisKerasCallback(run)

    class _AegisKerasCallback(Base):
        def on_epoch_end(self, epoch, logs=None):
            if logs:
                run.log(dict(logs), step=epoch + 1)

        def on_train_end(self, logs=None):
            pass

    return _AegisKerasCallback()


class AegisPyTorchHook:
    """
    Контекст-менеджер для PyTorch-обучения.
    """

    def __init__(self, run: "AegisRun", model=None):
        self._run = run
        self._model = model
        self._hooks = []

    def __enter__(self):
        if self._model is not None:
            self._register_grad_hooks()
        return self

    def __exit__(self, *args):
        for h in self._hooks:
            h.remove()
        self._hooks.clear()

    def log(self, metrics: dict, step: int = None):
        self._run.log(metrics, step=step)

    def _register_grad_hooks(self):
        try:
            import torch  # type: ignore
            for name, param in self._model.named_parameters():
                if param.requires_grad:
                    def make_hook(n):
                        def hook(grad):
                            if grad is not None:
                                self._run.log({
                                    f"grad/{n}/norm": grad.norm().item()
                                }, step=self._run.step)
                        return hook
                    h = param.register_hook(make_hook(name))
                    self._hooks.append(h)
        except ImportError:
            pass


class AegisSklearnWrapper:
    """
    Обёртка для sklearn-моделей.
    """

    def __init__(self, run: "AegisRun", model):
        self._run = run
        self._model = model

    def fit(self, X, y, **kwargs):
        import time
        t0 = time.perf_counter()
        self._model.fit(X, y, **kwargs)
        elapsed = time.perf_counter() - t0
        self._run.log({"fit_time_s": round(elapsed, 3)}, step=1)
        return self

    def score(self, X, y) -> float:
        score = self._model.score(X, y)
        metric_name = "accuracy"
        self._run.log({metric_name: round(score, 6)}, step=1)
        return score

    def predict(self, X):
        return self._model.predict(X)

    def predict_proba(self, X):
        return self._model.predict_proba(X)

    def __getattr__(self, name):
        return getattr(self._model, name)
