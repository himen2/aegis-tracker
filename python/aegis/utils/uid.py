"""
Aegis ML Tracker — утилиты для генерации уникальных ID запусков.
"""
import hashlib
import os
import random
import string
import time

_B36 = string.digits + string.ascii_lowercase


def _to_base36(n: int) -> str:
    if n == 0:
        return '0'
    result = []
    while n:
        result.append(_B36[n % 36])
        n //= 36
    return ''.join(reversed(result))


def generate_run_id() -> str:
    ts = int(time.time() * 1000)
    pid = os.getpid() % 1296
    rand = ''.join(random.choices(_B36, k=6))
    return f"{_to_base36(ts)}-{_to_base36(pid)}{rand}"


def config_fingerprint(config: dict) -> str:
    canonical = str(sorted(config.items()))
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]


def short_hash(text: str, length: int = 8) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:length]

