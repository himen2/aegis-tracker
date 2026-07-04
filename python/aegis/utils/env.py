"""
Aegis — определение рабочего окружения.
"""
import os
import sys
from typing import Optional

_ENV_CACHE: Optional[str] = None


def detect_environment() -> str:
    """Определяет среду выполнения. Результат кешируется в рамках процесса."""
    global _ENV_CACHE
    if _ENV_CACHE is not None:
        return _ENV_CACHE

    try:
        from IPython import get_ipython
        shell = get_ipython()
        if shell is None:
            result = 'terminal'
        elif 'google.colab' in sys.modules or 'COLAB_GPU' in os.environ:
            result = 'colab'
        elif shell.__class__.__name__ == 'ZMQInteractiveShell':
            # Jupyter Notebook, JupyterLab, VSCode Notebook, Google Colab kernel
            result = 'jupyter'
        else:
            result = 'ipython'
    except ImportError:
        result = 'terminal'

    _ENV_CACHE = result
    return _ENV_CACHE


def is_notebook() -> bool:
    return detect_environment() in ('colab', 'jupyter')


def is_colab() -> bool:
    return detect_environment() == 'colab'


def get_python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def get_platform_info() -> dict:
    import platform
    return {
        "python": get_python_version(),
        "os": platform.system(),
        "os_version": platform.version(),
        "machine": platform.machine(),
        "environment": detect_environment(),
    }


def get_backend_url(default: str = "http://localhost:8000") -> str:
    """Возвращает URL backend из env (для работы библиотеки на любом хосте)."""
    url = os.getenv("AEGIS_BASE_URL") or os.getenv("AEGIS_API_URL") or default
    return url.rstrip('/')


def get_dashboard_url(default: str = "http://localhost:5174") -> str:
    """Возвращает URL frontend/dashboard из env."""
    url = os.getenv("AEGIS_DASHBOARD_URL") or os.getenv("AEGIS_FRONTEND_URL") or default
    return url.rstrip('/')


def get_api_token() -> str:
    """Bearer-токен для привязки notebook-логов к аккаунту на сайте."""
    return (
        os.getenv("AEGIS_API_TOKEN")
        or os.getenv("AEGIS_BEARER_TOKEN")
        or ""
    ).strip()

