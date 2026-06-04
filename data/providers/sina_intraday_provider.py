"""Sina intraday minute provider."""
from __future__ import annotations

from typing import Any

import pandas as pd


class SinaIntradayProvider:
    """Fetch raw A-share intraday bars from Sina Finance."""

    source = "新浪财经"
    interval = "5分钟"

    def __init__(self, session: Any):
        self.session = session

    @staticmethod
    def sina_symbol(symbol: str) -> str:
        prefix = "sh" if str(symbol).startswith("6") else "sz"
        return f"{prefix}{symbol}"

    def fetch_raw(self, symbol: str) -> pd.DataFrame | None:
        sina_symbol = self.sina_symbol(symbol)
        url = (
            "https://quotes.sina.cn/cn/api/json_v2.php/"
            f"CN_MarketDataService.getKLineData?symbol={sina_symbol}"
            "&scale=5&ma=no&datalen=240"
        )
        response = self.session.get(url, timeout=10)
        if response.status_code != 200:
            return None
        data = response.json()
        if not data or not isinstance(data, list):
            return None
        df = pd.DataFrame(data)
        df.rename(columns={
            "day": "time",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
            "amount": "amount",
        }, inplace=True)
        return df
