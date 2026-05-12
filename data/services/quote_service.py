"""行情数据服务。"""
from __future__ import annotations

import logging
import re
from typing import Any

from data.providers.legacy_quote_provider import LegacyQuoteProvider


logger = logging.getLogger(__name__)


class QuoteDataService:
    """K线、实时行情、分时图与批量行情的业务入口。"""

    def __init__(self, provider: LegacyQuoteProvider | None = None):
        self.provider = provider or LegacyQuoteProvider()

    def get_stock_data(self, symbol: str, period: str = "1y", market: str = "CN"):
        symbol = self._normalize_symbol(symbol)
        if not symbol:
            return None
        return self.provider.get_stock_data(symbol, period=period, market=market)

    def get_realtime_quote(self, symbol: str, market: str = "CN") -> dict[str, Any] | None:
        symbol = self._normalize_symbol(symbol)
        if not symbol:
            return None
        return self.provider.get_realtime_quote(symbol, market)

    def get_intraday_data(self, symbol: str, market: str = "CN"):
        symbol = self._normalize_symbol(symbol)
        if not symbol or market != "CN":
            return None
        return self.provider.get_intraday_data(symbol, market)

    def get_batch_realtime_quotes(self, symbols: list[str], market: str = "CN") -> dict[str, dict]:
        normalized_symbols = [self._normalize_symbol(symbol) for symbol in symbols]
        normalized_symbols = [symbol for symbol in normalized_symbols if symbol]
        if not normalized_symbols:
            return {}
        return self.provider.get_batch_realtime_quotes(normalized_symbols, market)

    def get_stock_name(self, symbol: str, market: str = "CN") -> str:
        symbol = self._normalize_symbol(symbol)
        if not symbol:
            return ""
        return self.provider.get_stock_name(symbol, market)

    def get_index_realtime(self, symbol: str) -> dict[str, Any] | None:
        symbol = self._normalize_symbol(symbol)
        if not symbol:
            return None
        return self.provider.get_index_realtime(symbol)

    def get_preferred_source(self) -> str:
        return self.provider.get_preferred_source()

    def set_preferred_source(self, source: str) -> bool:
        return bool(self.provider.set_preferred_source(source))

    def fetch_multiple_stocks(self, stocks: list[dict], period: str = "1y", market: str = "CN", max_workers: int = 5):
        normalized_stocks = []
        for stock in stocks:
            code = self._normalize_symbol(stock.get("code", ""))
            if code:
                normalized_stocks.append({**stock, "code": code})
        if not normalized_stocks:
            return {}
        return self.provider.fetch_multiple_stocks(
            normalized_stocks,
            period=period,
            market=market,
            max_workers=max_workers,
        )

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        symbol = str(symbol or "").strip()
        if re.fullmatch(r"\d+(\.0+)?", symbol):
            symbol = symbol.split(".", 1)[0]
        return symbol.upper() if symbol.isascii() else symbol
