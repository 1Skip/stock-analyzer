"""个股基础资料服务。"""
from __future__ import annotations

import logging
import re

from config import CACHE_TTL_FUNDAMENTALS
from data.cache import JsonFileCache
from data.models import StockProfile
from data.providers.akshare_provider import AkShareProvider


logger = logging.getLogger(__name__)


class FundamentalDataService:
    """基础资料/估值服务，后续可继续挂公告、研报、新闻等 provider。"""

    def __init__(self, provider: AkShareProvider | None = None, cache: JsonFileCache | None = None):
        self.provider = provider or AkShareProvider()
        self.cache = cache or JsonFileCache("fundamentals", CACHE_TTL_FUNDAMENTALS)

    def get_stock_profile(self, symbol: str, market: str = "CN") -> dict | None:
        symbol = str(symbol or "").strip()
        if market != "CN" or not re.fullmatch(r"\d{6}", symbol):
            return None

        cache_key = f"{market}:{symbol}:profile"
        cached = self.cache.get(cache_key)
        if isinstance(cached, dict):
            source = str(cached.get("source") or "")
            if cached.get("industry") and cached.get("listing_date"):
                return cached
            if "腾讯行情" not in source:
                return cached

        profile = self.provider.get_stock_profile(symbol)
        if profile is None:
            return cached if isinstance(cached, dict) else None

        payload = profile.to_dict() if isinstance(profile, StockProfile) else profile
        self.cache.set(cache_key, payload)
        return payload
