"""数据层文件缓存。"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from config import RUNTIME_CACHE_DIR


_CACHE_LOCKS: dict[Path, threading.Lock] = {}
_CACHE_LOCKS_GUARD = threading.Lock()


def _get_lock(path: Path) -> threading.Lock:
    with _CACHE_LOCKS_GUARD:
        if path not in _CACHE_LOCKS:
            _CACHE_LOCKS[path] = threading.Lock()
        return _CACHE_LOCKS[path]


def _safe_key(key: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.:-]+", "_", key)


class JsonFileCache:
    """简单 JSON 文件缓存，按 namespace 聚合存储。"""

    def __init__(self, namespace: str, ttl_seconds: int, cache_dir: str | os.PathLike[str] | None = None):
        self.namespace = _safe_key(namespace)
        self.ttl = timedelta(seconds=ttl_seconds)
        self.path = Path(cache_dir or RUNTIME_CACHE_DIR) / f"{self.namespace}.json"

    def get(self, key: str) -> Any | None:
        payload = self._read()
        item = payload.get(_safe_key(key))
        if not item:
            return None
        try:
            updated_at = datetime.fromisoformat(item["updated_at"])
        except Exception:
            return None
        if datetime.now() - updated_at > self.ttl:
            return None
        return item.get("value")

    def set(self, key: str, value: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = _get_lock(self.path)
        with lock:
            payload = self._read_unlocked()
            payload[_safe_key(key)] = {
                "updated_at": datetime.now().isoformat(),
                "value": value,
            }
            tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
            with open(tmp_path, "w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False)
            os.replace(tmp_path, self.path)

    def _read(self) -> dict[str, Any]:
        lock = _get_lock(self.path)
        with lock:
            return self._read_unlocked()

    def _read_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as file:
                data = json.load(file)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

