"""
Aegis — системный монитор.
Собирает CPU, RAM, GPU-метрики без внешних зависимостей (только stdlib).
GPU через nvidia-smi (если доступен).
"""
import os
import sys
import subprocess
import threading
from typing import Dict, Optional


def _read_file(path: str) -> Optional[str]:
    try:
        with open(path, 'r') as f:
            return f.read().strip()
    except Exception:
        return None


def get_cpu_percent() -> Optional[float]:
    try:
        import aegis_core
        return float(aegis_core.get_cpu_percent())
    except ImportError:
        pass
    try:
        import psutil
        return psutil.cpu_percent(interval=0.1)
    except ImportError:
        pass
    if sys.platform.startswith('linux'):
        try:
            with open('/proc/stat', 'r') as f:
                line = f.readline()
            fields = list(map(int, line.split()[1:]))
            idle = fields[3]
            total = sum(fields)
            return round(100.0 * (1 - idle / total), 1) if total > 0 else None
        except Exception:
            pass
    return None


def get_memory_mb() -> Dict[str, Optional[float]]:
    try:
        import aegis_core
        dict_data = aegis_core.get_memory_mb()
        return dict_data
    except ImportError:
        pass
    try:
        import psutil
        vm = psutil.virtual_memory()
        return {
            "ram_used_mb": round(vm.used / 1024 / 1024, 1),
            "ram_total_mb": round(vm.total / 1024 / 1024, 1),
            "ram_percent": vm.percent,
        }
    except ImportError:
        pass
    if sys.platform.startswith('linux'):
        try:
            info = {}
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    k, v = line.split(':')
                    info[k.strip()] = int(v.split()[0])
            total = info.get('MemTotal', 0)
            free = info.get('MemAvailable', 0)
            used = total - free
            return {
                "ram_used_mb": round(used / 1024, 1),
                "ram_total_mb": round(total / 1024, 1),
                "ram_percent": round(100 * used / total, 1) if total else None,
            }
        except Exception:
            pass
    return {"ram_used_mb": None, "ram_total_mb": None, "ram_percent": None}


def get_gpu_metrics() -> Dict[str, Optional[float]]:
    result: Dict[str, Optional[float]] = {
        "gpu_util": None, "gpu_mem_used_mb": None,
        "gpu_mem_total_mb": None, "gpu_temp": None,
    }
    # NVIDIA via nvidia-smi
    try:
        out = subprocess.check_output(
            ["nvidia-smi",
             "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).decode().strip().split('\n')[0].split(',')
        if len(out) >= 4:
            result["gpu_util"] = float(out[0].strip())
            result["gpu_mem_used_mb"] = float(out[1].strip())
            result["gpu_mem_total_mb"] = float(out[2].strip())
            result["gpu_temp"] = float(out[3].strip())
            return result
    except Exception:
        pass
    # AMD via rocm-smi
    try:
        out = subprocess.check_output(
            ["rocm-smi", "--showuse", "--showmeminfo", "vram", "--csv"],
            stderr=subprocess.DEVNULL, timeout=3,
        ).decode().strip().splitlines()
        if len(out) > 1:
            row = out[1].split(',')
            if len(row) >= 3:
                result["gpu_util"] = float(row[1].strip().rstrip('%'))
                result["gpu_mem_used_mb"] = float(row[2].strip()) / 1024 / 1024
                return result
    except Exception:
        pass
    return result


class SystemProbe:
    def __init__(self, interval: float = 5.0):
        self._interval = interval
        self._latest: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._first_done = False  # первый снимок ещё не снят

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _collect(self) -> Dict[str, float]:
        metrics: Dict[str, float] = {}
        cpu = get_cpu_percent()
        if cpu is not None:
            metrics["sys/cpu_percent"] = cpu
        mem = get_memory_mb()
        for k, v in mem.items():
            if v is not None:
                metrics[f"sys/{k}"] = v
        gpu = get_gpu_metrics()
        for k, v in gpu.items():
            if v is not None:
                metrics[f"sys/{k}"] = v
        return metrics

    def _run(self):
        # Первый снимок — немедленно
        snap = self._collect()
        with self._lock:
            self._latest = snap
            self._first_done = True
        while not self._stop.wait(self._interval):
            snap = self._collect()
            with self._lock:
                self._latest = snap

    def get_latest(self) -> Dict[str, float]:
        with self._lock:
            return dict(self._latest)

    def snapshot(self) -> Dict[str, Optional[float]]:
        metrics: Dict[str, Optional[float]] = {}
        cpu = get_cpu_percent()
        if cpu is not None:
            metrics["sys/cpu_percent"] = cpu
        metrics.update({f"sys/{k}": v for k, v in get_memory_mb().items()})
        metrics.update({f"sys/{k}": v for k, v in get_gpu_metrics().items()})
        return {k: v for k, v in metrics.items() if v is not None}

