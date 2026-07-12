"""数据层文件缓存。"""
from __future__ import annotations

import json
import os
import base64
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping

from config import RUNTIME_CACHE_DIR
from data.file_lock import atomic_write_text, get_thread_lock, process_file_lock


logger = logging.getLogger(__name__)


def _safe_key(key: str) -> str:
    raw = str(key or "")
    if re.fullmatch(r"[0-9A-Za-z_.:-]+", raw):
        return raw
    encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
    return f"b64_{encoded}"


def _legacy_safe_key(key: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.:-]+", "_", str(key or ""))


class JsonFileCache:
    """简单 JSON 文件缓存，按 namespace 聚合存储。"""

    def __init__(self, namespace: str, ttl_seconds: int, cache_dir: str | os.PathLike[str] | None = None):
        self.namespace = _safe_key(namespace)
        self.ttl = timedelta(seconds=ttl_seconds)
        self.path = Path(cache_dir or RUNTIME_CACHE_DIR) / f"{self.namespace}.json"

    def get(self, key: str) -> Any | None:
        return self.get_many([key]).get(str(key or ""))

    def get_many(self, keys: Iterable[str]) -> dict[str, Any]:
        """Read multiple cache keys with one file load."""
        payload = self._read()
        now = datetime.now()
        values: dict[str, Any] = {}
        for key in keys:
            raw_key = str(key or "")
            item = payload.get(_safe_key(raw_key))
            if not item:
                item = payload.get(_legacy_safe_key(raw_key))
            if not self._is_fresh_item(item, now, key=raw_key):
                continue
            values[raw_key] = item.get("value")
        return values

    def set(self, key: str, value: Any) -> None:
        self.set_many({key: value})

    def set_many(self, values: Mapping[str, Any]) -> None:
        """Update multiple cache keys with one read-modify-write cycle."""
        if not values:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = get_thread_lock(self.path)
        with lock:
            with process_file_lock(self.path):
                payload = self._read_unlocked()
                now = datetime.now()
                self._drop_expired_items(payload, now)
                updated_at = now.isoformat()
                for key, value in values.items():
                    payload[_safe_key(str(key or ""))] = {
                        "updated_at": updated_at,
                        "value": value,
                    }
                atomic_write_text(self.path, json.dumps(payload, ensure_ascii=False))

    def compact(self) -> dict[str, int]:
        """Remove expired or malformed entries without changing fresh values."""
        if not self.path.exists():
            return {"removed": 0, "remaining": 0}
        lock = get_thread_lock(self.path)
        with lock:
            with process_file_lock(self.path):
                payload = self._read_unlocked()
                removed = self._drop_expired_items(payload, datetime.now())
                if removed:
                    atomic_write_text(self.path, json.dumps(payload, ensure_ascii=False))
                return {"removed": removed, "remaining": len(payload)}

    def delete(self, key: str) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = get_thread_lock(self.path)
        with lock:
            with process_file_lock(self.path):
                payload = self._read_unlocked()
                compacted = self._drop_expired_items(payload, datetime.now())
                safe_key = _safe_key(key)
                legacy_key = _legacy_safe_key(key)
                removed = False
                for candidate in {safe_key, legacy_key, str(key or "")}:
                    if candidate in payload:
                        payload.pop(candidate, None)
                        removed = True
                if not removed and not compacted:
                    return False
                atomic_write_text(self.path, json.dumps(payload, ensure_ascii=False))
                return removed

    def _read(self) -> dict[str, Any]:
        lock = get_thread_lock(self.path)
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
            logger.warning("读取 JSON 缓存失败，按空缓存处理: %s", self.path, exc_info=True)
            return {}

    def _drop_expired_items(self, payload: dict[str, Any], now: datetime) -> int:
        expired = [key for key, item in payload.items() if not self._is_fresh_item(item, now, key=key)]
        for key in expired:
            payload.pop(key, None)
        return len(expired)

    def _is_fresh_item(self, item: Any, now: datetime, *, key: str) -> bool:
        if not isinstance(item, dict):
            return False
        try:
            updated_at = datetime.fromisoformat(item["updated_at"])
        except Exception:
            logger.debug("缓存条目时间戳无效: path=%s key=%s", self.path, key, exc_info=True)
            return False
        return now - updated_at <= self.ttl
