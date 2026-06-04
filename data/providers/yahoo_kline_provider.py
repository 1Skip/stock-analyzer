"""Yahoo Finance K-line provider wrapper."""
from __future__ import annotations

import time
from typing import Any

import pandas as pd


class YahooKlineProvider:
    """Fetch history from yfinance while keeping legacy normalization."""

    source = "Yahoo Finance"

    def __init__(self, yf_module: Any):
        self.yf = yf_module

    @staticmethod
    def cn_symbol(symbol: str) -> str:
        symbol = str(symbol)
        if "." in symbol:
            return symbol
        if symbol.startswith(("600", "601", "603", "605", "688")):
            return f"{symbol}.SS"
        if symbol.startswith(("000", "001", "002", "003", "300", "301")):
            return f"{symbol}.SZ"
        return f"{symbol}.SS"

    @staticmethod
    def _normalize(data: pd.DataFrame | None) -> pd.DataFrame | None:
        if data is None or getattr(data, "empty", True) or len(data) < 10:
            return None
        data = data.copy()
        data.columns = [str(col).lower().replace(" ", "_") for col in data.columns]
        data.attrs["adjust_method"] = "adjusted close\uff08yfinance\uff09"
        data.attrs["volume_unit"] = "share"
        return data

    def fetch(self, symbol: str, period: str, *, interval: str = "1d", market: str = "US") -> pd.DataFrame | None:
        market = str(market or "US").upper()
        if market == "HK":
            yf_symbol = f"{symbol}.HK"
        elif market == "CN":
            yf_symbol = self.cn_symbol(symbol)
        else:
            yf_symbol = symbol
        data = self.yf.Ticker(yf_symbol).history(period=period, interval=interval)
        return self._normalize(data)

    def fetch_cn_with_retry(self, symbol: str, period: str, *, max_retries: int = 2) -> pd.DataFrame | None:
        candidates = [self.cn_symbol(symbol)]
        if candidates[0].endswith(".SS"):
            candidates.append(f"{symbol}.SZ")
        elif candidates[0].endswith(".SZ"):
            candidates.append(f"{symbol}.SS")
        for attempt in range(max_retries):
            for yf_symbol in dict.fromkeys(candidates):
                try:
                    data = self.yf.Ticker(yf_symbol).history(period=period)
                    normalized = self._normalize(data)
                    if normalized is not None:
                        return normalized
                except Exception:
                    continue
            if attempt < max_retries - 1:
                time.sleep(1)
        return None
