"""Yahoo Finance quote/info provider wrapper."""
from __future__ import annotations

from typing import Any


class YahooQuoteProvider:
    """Fetch Yahoo Finance info and quote fallbacks with legacy field names."""

    source = "Yahoo Finance"

    def __init__(self, yf_module: Any):
        self.yf = yf_module

    @staticmethod
    def symbol_for_market(symbol: str, market: str = "US") -> str:
        market = str(market or "US").upper()
        symbol = str(symbol)
        if market == "HK":
            return f"{symbol}.HK"
        if market == "CN":
            if symbol.startswith(("600", "601", "603", "605", "688")):
                return f"{symbol}.SS"
            if symbol.startswith(("000", "001", "002", "003", "300", "301")):
                return f"{symbol}.SZ"
            return f"{symbol}.SS"
        return symbol

    @staticmethod
    def index_symbol(symbol: str) -> str:
        yf_map = {"000001": "^SSEC", "399001": "399001.SZ", "399006": "399006.SZ"}
        return yf_map.get(str(symbol), f"{symbol}.SS")

    def fetch_info(self, symbol: str, market: str = "US") -> dict[str, Any] | None:
        info = self.yf.Ticker(self.symbol_for_market(symbol, market)).info
        return info if isinstance(info, dict) else None

    def fetch_quote(self, symbol: str, market: str = "US") -> dict[str, Any] | None:
        ticker = self.yf.Ticker(self.symbol_for_market(symbol, market))
        hist = ticker.history(period="5d")
        info = ticker.info or {}
        if hist is None or getattr(hist, "empty", True):
            return None
        latest = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) > 1 else latest
        latest_close = float(latest["Close"])
        prev_close = float(prev["Close"])
        return {
            "symbol": symbol,
            "name": info.get("shortName", symbol),
            "price": latest_close,
            "open": float(latest["Open"]),
            "high": float(latest["High"]),
            "low": float(latest["Low"]),
            "volume": float(latest["Volume"]),
            "prev_close": prev_close,
            "change": ((latest_close - prev_close) / prev_close * 100) if prev_close else 0.0,
        }

    def fetch_index_quote(self, symbol: str) -> dict[str, Any] | None:
        ticker = self.yf.Ticker(self.index_symbol(symbol))
        info = ticker.info or {}
        hist = ticker.history(period="5d")
        if hist is None or len(hist) < 2:
            return None
        latest = hist.iloc[-1]
        prev = hist.iloc[-2]
        latest_close = float(latest["Close"])
        prev_close = float(prev["Close"])
        return {
            "symbol": symbol,
            "name": info.get("shortName", symbol),
            "price": latest_close,
            "change_pct": float((latest_close / prev_close - 1) * 100) if prev_close else 0.0,
            "prev_close": prev_close,
        }
