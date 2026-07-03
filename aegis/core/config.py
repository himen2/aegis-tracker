"""
Aegis — умный объект конфигурации.
Поддерживает доступ и через dict, и через атрибуты:
    run.config["lr"] == run.config.lr == 0.001
"""
from typing import Any, Iterator


class AegisConfig:
    """
    Объект конфигурации эксперимента.
    """

    def __init__(self, data: dict = None):
        object.__setattr__(self, '_data', dict(data or {}))

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any):
        self._data[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __iter__(self) -> Iterator:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def update(self, d: dict):
        self._data.update(d)

    def __getattr__(self, key: str) -> Any:
        data = object.__getattribute__(self, '_data')
        if key in data:
            return data[key]
        raise AttributeError(f"AegisConfig: нет параметра '{key}'")

    def __setattr__(self, key: str, value: Any):
        if key.startswith('_'):
            object.__setattr__(self, key, value)
        else:
            self._data[key] = value

    def __delattr__(self, key: str):
        if key in self._data:
            del self._data[key]
        else:
            raise AttributeError(f"AegisConfig: нет параметра '{key}'")

    def to_dict(self) -> dict:
        return dict(self._data)

    def __repr__(self) -> str:
        items = ", ".join(f"{k}={v!r}" for k, v in self._data.items())
        return f"AegisConfig({{{items}}})"

    def __str__(self) -> str:
        return self.__repr__()

