"""
Aegis — Менеджер артефактов.
Загрузка и версионирование весов моделей, конфигов и файлов.
"""
import os
import shutil
import hashlib
import json
import threading
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone


def _file_hash(path: str, algorithm: str = "sha256") -> str:
    """Вычисляет хэш файла для версионирования."""
    h = hashlib.new(algorithm)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _human_size(size_bytes: int) -> str:
    """Форматирует размер файла в читабельный вид."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


class ArtifactManager:
    """
    Менеджер артефактов для AegisRun.

    Пример использования:
        run = aegis.init(project="cv")
        run.log_artifact("best_model.pth", type="model")
        run.log_artifact("config.yaml", type="config")
        run.log_artifact("predictions.csv", type="output")
    """

    def __init__(self, run_id: str, project: str, base_dir: Optional[str] = None):
        self._run_id = run_id
        self._project = project
        self._artifacts: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

        if base_dir is None:
            home = os.path.expanduser("~")
            base_dir = os.path.join(home, ".aegis", "artifacts")

        self._base_dir = os.path.join(base_dir, project, run_id)
        os.makedirs(self._base_dir, exist_ok=True)

    def log_artifact(
        self,
        path: str,
        type: str = "file",
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Сохраняет артефакт (файл) в хранилище Aegis.

        Args:
            path:     Путь к файлу (абсолютный или относительный).
            type:     Тип артефакта: "model", "config", "output", "checkpoint", "file".
            name:     Человекочитаемое имя (по умолчанию — имя файла).
            metadata: Дополнительные метаданные (dict).

        Returns:
            Dict с информацией о сохранённом артефакте.
        """
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Артефакт не найден: {path}")

        file_name = name or os.path.basename(path)
        file_size = os.path.getsize(path)
        file_hash = _file_hash(path)

        # Копируем файл в хранилище
        dest_dir = os.path.join(self._base_dir, type)
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, f"{file_hash}_{os.path.basename(path)}")
        shutil.copy2(path, dest_path)

        artifact_info = {
            "name": file_name,
            "type": type,
            "original_path": os.path.abspath(path),
            "stored_path": dest_path,
            "size": file_size,
            "size_human": _human_size(file_size),
            "hash": file_hash,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        with self._lock:
            self._artifacts.append(artifact_info)
            # Записываем индекс артефактов
            index_path = os.path.join(self._base_dir, "artifacts.json")
            with open(index_path, "w", encoding="utf-8") as f:
                json.dump(self._artifacts, f, indent=2, ensure_ascii=False)

        try:
            print(
                f"\033[1m\033[91m[AEGIS]\033[0m  artifact saved: "
                f"{file_name} ({artifact_info['size_human']}) "
                f"type={type} hash={file_hash}"
            )
        except Exception:
            pass

        return artifact_info

    def log_directory(
        self,
        dir_path: str,
        type: str = "output",
        name: Optional[str] = None,
        extensions: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Сохраняет все файлы из директории.

        Args:
            dir_path:    Путь к директории.
            type:        Тип артефакта.
            name:        Префикс имени.
            extensions:  Фильтр по расширениям (например, [".pth", ".pt"]).
        """
        if not os.path.isdir(dir_path):
            raise NotADirectoryError(f"Директория не найдена: {dir_path}")

        results = []
        for root, _, files in os.walk(dir_path):
            for filename in files:
                if extensions:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext not in extensions:
                        continue
                full_path = os.path.join(root, filename)
                artifact_name = f"{name}/{filename}" if name else filename
                result = self.log_artifact(full_path, type=type, name=artifact_name)
                results.append(result)

        return results

    @property
    def artifacts(self) -> List[Dict[str, Any]]:
        """Возвращает список всех сохранённых артефактов."""
        with self._lock:
            return list(self._artifacts)

    def get_artifact(self, name: str) -> Optional[Dict[str, Any]]:
        """Находит артефакт по имени."""
        with self._lock:
            for art in self._artifacts:
                if art["name"] == name:
                    return art
        return None

    def summary(self) -> Dict[str, Any]:
        """Возвращает сводку по артефактам."""
        with self._lock:
            total_size = sum(a["size"] for a in self._artifacts)
            by_type: Dict[str, int] = {}
            for a in self._artifacts:
                by_type[a["type"]] = by_type.get(a["type"], 0) + 1
            return {
                "total_artifacts": len(self._artifacts),
                "total_size": _human_size(total_size),
                "by_type": by_type,
            }
