"""
Aegis — Детектирование распределённого обучения (DDP/DeepSpeed).
Автоматически определяет multi-GPU сетап и управляет логированием.
"""
import os
from typing import Optional


def get_rank() -> int:
    """Возвращает текущий rank процесса (0 = главная нода)."""
    for var in ("RANK", "SLURM_PROCID", "PMI_RANK", "OMPI_COMM_WORLD_RANK"):
        val = os.environ.get(var)
        if val is not None:
            try:
                return int(val)
            except ValueError:
                pass
    return 0


def get_local_rank() -> int:
    """Возвращает локальный rank на текущей ноде."""
    for var in ("LOCAL_RANK", "SLURM_LOCALID", "OMPI_COMM_WORLD_LOCAL_RANK"):
        val = os.environ.get(var)
        if val is not None:
            try:
                return int(val)
            except ValueError:
                pass
    return 0


def get_world_size() -> int:
    """Возвращает количество процессов."""
    for var in ("WORLD_SIZE", "SLURM_NTASKS", "PMI_SIZE", "OMPI_COMM_WORLD_SIZE"):
        val = os.environ.get(var)
        if val is not None:
            try:
                return int(val)
            except ValueError:
                pass
    return 1


def is_distributed() -> bool:
    """Проверяет, запущен ли процесс в DDP-режиме."""
    return get_world_size() > 1


def is_main_process() -> bool:
    """True только для rank 0 (главный процесс, который должен логировать)."""
    return get_rank() == 0


def get_ddp_info() -> dict:
    """Возвращает полную информацию о DDP-сетапе."""
    return {
        "rank": get_rank(),
        "local_rank": get_local_rank(),
        "world_size": get_world_size(),
        "is_distributed": is_distributed(),
        "is_main_process": is_main_process(),
    }
