"""Cached corporate-action service with explicit missing-source status."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from config import (
    CACHE_TTL_CORPORATE_ACTIONS,
    CORPORATE_ACTION_FETCH_TIMEOUT_SECONDS,
    RUNTIME_CACHE_DIR,
)
from data.cache import JsonFileCache
from data.providers.corporate_action_provider import AkShareCorporateActionProvider


class CorporateActionService:
    """Return real normalized events; never synthesize missing company actions."""

    def __init__(
        self,
        *,
        provider: AkShareCorporateActionProvider | None = None,
        cache: JsonFileCache | None = None,
        cache_dir: str | Path | None = None,
        timeout_seconds: float = CORPORATE_ACTION_FETCH_TIMEOUT_SECONDS,
    ):
        self.provider = provider or AkShareCorporateActionProvider()
        self.cache = cache or JsonFileCache(
            "corporate_action_history",
            CACHE_TTL_CORPORATE_ACTIONS,
            cache_dir=cache_dir or RUNTIME_CACHE_DIR,
        )
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self._memory: dict[str, dict[str, Any]] = {}

    def get_events(self, symbol: str, *, refresh: bool = False) -> dict[str, Any]:
        symbol_text = str(symbol or "").strip().zfill(6)
        if not refresh and symbol_text in self._memory:
            return dict(self._memory[symbol_text])
        if not refresh:
            cached = self.cache.get(symbol_text)
            if isinstance(cached, dict) and isinstance(cached.get("events"), list):
                result = {**cached, "cache_hit": True}
                self._memory[symbol_text] = result
                return dict(result)

        result = self.provider.get_events(
            symbol_text,
            timeout_seconds=self.timeout_seconds,
        )
        if not isinstance(result, dict):
            result = {
                "status": "source_failed",
                "symbol": symbol_text,
                "source": "巨潮资讯/AKShare",
                "events": [],
                "event_count": 0,
                "errors": ["公司行为 provider 未返回有效结果"],
            }
        result = {**result, "cache_hit": False}
        self._memory[symbol_text] = result
        if result.get("status") == "ok":
            self.cache.set(symbol_text, result)
        return dict(result)

    def get_due_events(
        self,
        symbol: str,
        *,
        as_of_date: str,
        held_since: str | None = None,
    ) -> dict[str, Any]:
        result = self.get_events(symbol)
        due = []
        for event in result.get("events") or []:
            if not isinstance(event, dict):
                continue
            effective_date = str(event.get("effective_date") or "")[:10]
            eligibility_date = str(event.get("record_date") or effective_date)[:10]
            if not effective_date or effective_date > as_of_date:
                continue
            if held_since and eligibility_date and eligibility_date < held_since:
                continue
            due.append(dict(event))
        return {
            **result,
            "events": due,
            "due_event_count": len(due),
            "total_event_count": int(result.get("event_count") or len(result.get("events") or [])),
        }
