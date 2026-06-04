"""Eastmoney intraday minute provider via AKShare."""
from __future__ import annotations

from typing import Any

import pandas as pd


class EastmoneyIntradayProvider:
    """Fetch raw A-share 1-minute intraday bars from Eastmoney/AKShare."""

    source = "东方财富1分钟分时"
    interval = "1分钟"

    def __init__(self, ak_module: Any):
        self.ak = ak_module

    def fetch_raw(self, symbol: str) -> pd.DataFrame | None:
        df = self.ak.stock_zh_a_hist_min_em(symbol=symbol, period="1", adjust="")
        if df is None or len(df) <= 0:
            return None
        df = df.copy()
        rename_map = {
            "时间": "time",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
            "均价": "avg_price",
        }
        df.rename(columns=rename_map, inplace=True)
        if "time" not in df.columns and len(df.columns) >= 6:
            positional = ["time", "open", "close", "high", "low", "volume", "amount", "avg_price"]
            df = df.rename(columns={old: positional[i] for i, old in enumerate(df.columns[:len(positional)])})
        return df
