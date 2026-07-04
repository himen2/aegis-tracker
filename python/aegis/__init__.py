"""Aegis — ML experiment tracking library."""

import os
import urllib.request
import urllib.error

from .core.run import AegisRun
from .core.config import AegisConfig
from .utils.uid import generate_run_id, config_fingerprint, short_hash
from .utils.env import (
    detect_environment,
    is_notebook,
    is_colab,
    get_platform_info,
    get_backend_url,
    get_dashboard_url,
)
from .utils.timer import AegisTimer
from .utils.ddp import is_main_process, is_distributed, get_rank, get_world_size, get_ddp_info
from .metrics.collector import MetricCollector
from .metrics.system import SystemProbe
from .metrics.alerts import AlertManager, AlertRule
from .storage.local_db import LocalStore
from .storage.artifacts import ArtifactManager
from .display.renderer import JupyterRenderer, TerminalRenderer
from .hooks import AegisKerasCallback, AegisPyTorchHook, AegisSklearnWrapper
from .transport import AegisHTTP, SmartSender

__version__ = "0.1.0"

# Module-level session: set by login()/configure(), used by init()
_session: dict = {}


def ping(base_url: str = None, timeout: float = 5.0) -> bool:
    """Проверяет, доступен ли backend Aegis из текущего окружения."""
    url = (base_url or get_backend_url()).rstrip('/') + "/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except Exception:
        return False


def configure(
    api_key: str = None,
    base_url: str = None,
    dashboard_url: str = None,
    validate: bool = True,
) -> dict:
    """Настраивает библиотеку для работы из любого Jupyter/Notebook/Lab окружения.

    Пример::

        aegis.configure(
            api_key="aegis_live_xxx",
            base_url="https://api.example.com",
            dashboard_url="https://app.example.com",
        )
    """
    resolved_base = (base_url or get_backend_url()).rstrip('/')
    resolved_dashboard = (dashboard_url or get_dashboard_url()).rstrip('/')
    resolved_key = (api_key or os.getenv("AEGIS_API_TOKEN") or "").strip()

    if validate and not ping(resolved_base):
        raise RuntimeError(
            f"Aegis backend недоступен по адресу {resolved_base}. "
            "Укажите публичный URL backend, доступный из текущего ноутбука."
        )

    _session["base_url"] = resolved_base
    _session["dashboard_url"] = resolved_dashboard
    if resolved_key:
        _session["token"] = resolved_key

    os.environ["AEGIS_BASE_URL"] = resolved_base
    os.environ["AEGIS_DASHBOARD_URL"] = resolved_dashboard
    if resolved_key:
        os.environ["AEGIS_API_TOKEN"] = resolved_key

    result = {
        "base_url": resolved_base,
        "dashboard_url": resolved_dashboard,
        "authenticated": bool(resolved_key),
        "reachable": True,
    }
    print(
        f"[Aegis] configured: backend={resolved_base} dashboard={resolved_dashboard} "
        f"auth={'yes' if resolved_key else 'no'}"
    )
    return result


def login(api_key: str, base_url: str = None, dashboard_url: str = None) -> None:
    """Войти в аккаунт с помощью API-ключа.

    Пример::

        aegis.login("aegis_live_xYz...")
        run = aegis.init(project="my_notebook", name="exp_1")
    """
    configure(api_key=api_key, base_url=base_url, dashboard_url=dashboard_url, validate=False)
    print(f"[Aegis] API ключ сохранен (оканчивается на {api_key[-4:]})")
    return None


def logout() -> None:
    """Очистить сохранённый токен."""
    _session.clear()
    os.environ.pop("AEGIS_API_TOKEN", None)
    os.environ.pop("AEGIS_BASE_URL", None)
    os.environ.pop("AEGIS_DASHBOARD_URL", None)
    print("[Aegis] Выход выполнен")


def init(
    project: str,
    name: str = None,
    config: dict = None,
    tags: list = None,
    notes: str = None,
    base_url: str = None,
    api_token: str = None,
    smoothing: float = 0.0,
    log_system: bool = True,
    display_interval: int = 1,
    db_path: str = None,
    ddp_aware: bool = True,
) -> AegisRun:
    """Инициализирует новый запуск эксперимента.

    Args:
        ddp_aware:  Если True, автоматически определяет DDP и логирует только с rank 0.
    """
    # Use session token from login() if not explicitly provided
    resolved_token = api_token if api_token is not None else _session.get("token")
    resolved_url = base_url or _session.get("base_url")
    return AegisRun(
        project=project,
        name=name,
        config=config,
        tags=tags,
        notes=notes,
        base_url=resolved_url,
        api_token=resolved_token,
        smoothing=smoothing,
        log_system=log_system,
        display_interval=display_interval,
        db_path=db_path,
        ddp_aware=ddp_aware,
    )


__all__ = [
    "__version__",
    "ping",
    "configure",
    "login",
    "logout",
    "init",
    "AegisRun",
    "AegisConfig",
    "generate_run_id",
    "config_fingerprint",
    "short_hash",
    "detect_environment",
    "is_notebook",
    "is_colab",
    "get_platform_info",
    "is_main_process",
    "is_distributed",
    "get_rank",
    "get_world_size",
    "get_ddp_info",
    "AegisTimer",
    "MetricCollector",
    "SystemProbe",
    "AlertManager",
    "AlertRule",
    "LocalStore",
    "ArtifactManager",
    "JupyterRenderer",
    "TerminalRenderer",
    "AegisKerasCallback",
    "AegisPyTorchHook",
    "AegisSklearnWrapper",
    "AegisHTTP",
    "SmartSender",
]
