"""Tencent realtime quote provider."""
from __future__ import annotations

from typing import Any, Callable


class TencentRealtimeProvider:
    """Fetch A-share realtime quotes from Tencent lightweight quote endpoint."""

    source = "腾讯行情"

    def __init__(self, requests_module: Any, safe_float: Callable[[Any], float | None]):
        self.requests = requests_module
        self.safe_float = safe_float

    @staticmethod
    def tencent_code(symbol: str) -> str:
        if symbol.startswith("6"):
            return f"sh{symbol}"
        if symbol.startswith(("4", "8")):
            return f"bj{symbol}"
        return f"sz{symbol}"

    def fetch_batch(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        symbols = [str(symbol or "").strip() for symbol in symbols if symbol]
        if not symbols:
            return {}
        code_to_symbol = {self.tencent_code(symbol): symbol for symbol in symbols}
        response = self.requests.get(
            "https://qt.gtimg.cn/q=" + ",".join(code_to_symbol.keys()),
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://stockapp.finance.qq.com/"},
            timeout=5,
        )
        if response.status_code != 200:
            return {}

        result: dict[str, dict[str, Any]] = {}
        wanted = set(symbols)
        for line in response.text.splitlines():
            raw = line.split('"', 2)[1] if '"' in line else ""
            parts = raw.split("~")
            if len(parts) < 46:
                continue
            code = parts[2] if len(parts) > 2 else ""
            symbol = code[-6:] if code else ""
            if symbol not in wanted:
                continue
            price = self.safe_float(parts[3])
            prev_close = self.safe_float(parts[4])
            change_pct = self.safe_float(parts[32])
            if change_pct is None and price is not None and prev_close:
                change_pct = (price / prev_close - 1) * 100
            result[symbol] = {
                "symbol": symbol,
                "name": parts[1] or symbol,
                "price": price,
                "change_pct": change_pct,
                "open": self.safe_float(parts[5]),
                "prev_close": prev_close,
                "high": self.safe_float(parts[33]),
                "low": self.safe_float(parts[34]),
                "volume": self.safe_float(parts[6]),
                "turnover_rate": self.safe_float(parts[38]),
                "market_cap": (self.safe_float(parts[45]) or 0) * 1e8 if self.safe_float(parts[45]) else None,
                "source": self.source,
            }
        return result
