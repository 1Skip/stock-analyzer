"""现有行情获取器的 provider 适配层。

阶段 2 先把 UI 与 `data_fetcher.py` 解耦；后续再把新浪、腾讯、AKShare 等源
从 `StockDataFetcher` 内部逐步拆成独立 provider。
"""
from __future__ import annotations

from data_fetcher import StockDataFetcher


class LegacyQuoteProvider:
    """把现有 StockDataFetcher 暴露为标准行情 provider。"""

    def __init__(self, fetcher: StockDataFetcher | None = None):
        self.fetcher = fetcher or StockDataFetcher()

    def get_stock_data(self, symbol: str, period: str = "1y", market: str = "CN", adjust: str = ""):
        return self.fetcher.get_stock_data(symbol, period=period, market=market, adjust=adjust)

    def get_realtime_quote(self, symbol: str, market: str = "CN"):
        return self.fetcher.get_realtime_quote(symbol, market)

    def get_intraday_data(self, symbol: str, market: str = "CN"):
        return self.fetcher.get_intraday_data(symbol, market)

    def get_batch_realtime_quotes(self, symbols: list[str], market: str = "CN"):
        if market != "CN":
            return {}
        return self.fetcher.get_batch_realtime_quotes(symbols)

    def get_stock_name(self, symbol: str, market: str = "CN"):
        return self.fetcher.get_stock_name(symbol, market)

    def get_index_realtime(self, symbol: str):
        return self.fetcher.get_index_realtime(symbol)

    def get_preferred_source(self):
        return self.fetcher.get_preferred_source()

    def set_preferred_source(self, source: str):
        return self.fetcher.set_preferred_source(source)

    def fetch_multiple_stocks(self, stocks: list[dict], period: str = "1y", market: str = "CN", max_workers: int = 5):
        return StockDataFetcher.fetch_multiple_stocks(
            stocks,
            period=period,
            market=market,
            max_workers=max_workers,
        )
