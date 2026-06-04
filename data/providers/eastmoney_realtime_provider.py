"""Eastmoney realtime quote provider via AKShare."""
from __future__ import annotations

from typing import Any, Callable


def _first(row: Any, *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


class EastmoneyRealtimeProvider:
    """Fetch A-share realtime quotes from Eastmoney/AKShare spot snapshot."""

    source = "\u4e1c\u65b9\u8d22\u5bcc\u5b9e\u65f6\u884c\u60c5"

    def __init__(self, ak_module: Any, safe_float: Callable[[Any], float | None]):
        self.ak = ak_module
        self.safe_float = safe_float

    def fetch_batch(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        symbols = [str(symbol or "").strip() for symbol in symbols if symbol]
        if not symbols:
            return {}
        spot_df = self.ak.stock_zh_a_spot_em()
        if spot_df is None or getattr(spot_df, "empty", True):
            return {}

        wanted = set(symbols)
        result: dict[str, dict[str, Any]] = {}
        for _, row in spot_df.iterrows():
            symbol = str(_first(row, "代码", "code") or "").strip()
            if symbol not in wanted:
                continue
            result[symbol] = {
                "symbol": symbol,
                "name": _first(row, "名称", "name") or symbol,
                "price": self.safe_float(_first(row, "最新价", "price")),
                "change_pct": self.safe_float(_first(row, "涨跌幅", "change_pct")),
                "open": self.safe_float(_first(row, "今开", "open")),
                "prev_close": self.safe_float(_first(row, "昨收", "prev_close")),
                "high": self.safe_float(_first(row, "最高", "high")),
                "low": self.safe_float(_first(row, "最低", "low")),
                "volume": self.safe_float(_first(row, "成交量", "volume")),
                "turnover_rate": self.safe_float(_first(row, "换手率", "turnover_rate")),
                "market_cap": self.safe_float(_first(row, "总市值", "market_cap")),
                "source": self.source,
            }
        return result
