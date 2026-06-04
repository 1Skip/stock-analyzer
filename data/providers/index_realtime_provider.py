"""Realtime index quote providers."""
from __future__ import annotations

import re
from typing import Any

from data.providers.sina_realtime_provider import HEADERS


class SinaIndexRealtimeProvider:
    """Fetch A-share index realtime quote from Sina Finance."""

    def __init__(self, session: Any):
        self.session = session

    @staticmethod
    def sina_code(symbol: str) -> str:
        symbol = str(symbol)
        if symbol.startswith(("000", "600")):
            return f"sh{symbol}"
        if symbol.startswith("899"):
            return f"bj{symbol}"
        return f"sz{symbol}"

    @staticmethod
    def parse_quote(symbol: str, raw: str) -> dict[str, Any] | None:
        data = raw.split(",") if raw else []
        if len(data) < 4:
            return None
        try:
            price = float(data[3]) if data[3] else 0
            prev_close = float(data[2]) if data[2] else 1
        except (TypeError, ValueError):
            return None
        return {
            "symbol": symbol,
            "name": data[0],
            "price": price,
            "change_pct": (price / prev_close - 1) * 100 if prev_close else 0,
            "prev_close": prev_close,
        }

    def fetch_quote(self, symbol: str, timeout: int | float = 2) -> dict[str, Any] | None:
        url = f"https://hq.sinajs.cn/list={self.sina_code(symbol)}"
        response = self.session.get(url, headers=HEADERS, timeout=timeout)
        if response.status_code != 200:
            return None
        match = re.search(r'"([^"]*)"', response.text)
        if not match:
            return None
        return self.parse_quote(symbol, match.group(1))
