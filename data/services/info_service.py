"""个股扩展信息服务。"""
from __future__ import annotations

import re

from config import CACHE_TTL_STOCK_EXTENDED_INFO
from data.cache import JsonFileCache
from data.providers.akshare_info_provider import AkShareInfoProvider


class StockInfoService:
    """财务摘要、资金流、新闻等扩展信息服务。"""

    def __init__(self, provider: AkShareInfoProvider | None = None, cache: JsonFileCache | None = None):
        self.provider = provider or AkShareInfoProvider()
        self.cache = cache or JsonFileCache("stock_extended_info", CACHE_TTL_STOCK_EXTENDED_INFO)

    def get_stock_extended_info(self, symbol: str, market: str = "CN") -> dict | None:
        symbol = str(symbol or "").strip()
        if market != "CN" or not re.fullmatch(r"\d{6}", symbol):
            return None

        cache_key = f"{market}:{symbol}:extended"
        cached = self.cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

        payload = self.provider.get_stock_extended_info(symbol)
        self.cache.set(cache_key, payload)
        return payload

