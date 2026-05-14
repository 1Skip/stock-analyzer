"""个股基础资料服务。"""
from __future__ import annotations

import logging
import re

from config import CACHE_TTL_FUNDAMENTALS
from data.cache import JsonFileCache
from data.models import StockProfile
from data.providers.akshare_provider import AkShareProvider, _find_profile_index_item, _is_missing_profile_value


logger = logging.getLogger(__name__)


class FundamentalDataService:
    """基础资料/估值服务，后续可继续挂公告、研报、新闻等 provider。"""

    def __init__(self, provider: AkShareProvider | None = None, cache: JsonFileCache | None = None):
        self.provider = provider or AkShareProvider()
        self.cache = cache or JsonFileCache("fundamentals", CACHE_TTL_FUNDAMENTALS)
        self.index_cache = JsonFileCache("fundamental_profile_index", CACHE_TTL_FUNDAMENTALS)

    def get_stock_profile(self, symbol: str, market: str = "CN") -> dict | None:
        symbol = str(symbol or "").strip()
        if market != "CN" or not re.fullmatch(r"\d{6}", symbol):
            return None

        cache_key = f"{market}:{symbol}:profile"
        cached = self.cache.get(cache_key)
        if isinstance(cached, dict):
            cached = self._merge_profile_index_fields(cached)
            if not _is_missing_profile_value(cached.get("industry")) and not _is_missing_profile_value(cached.get("listing_date")):
                return cached
            source = str(cached.get("source") or "")
            if "腾讯行情" not in source:
                return cached

        profile = self.provider.get_stock_profile(symbol)
        if profile is None:
            if isinstance(cached, dict):
                return self._merge_profile_index_fields(cached)
            index_item = _find_profile_index_item(self.get_stock_profile_index(), symbol)
            return self._profile_from_index_item(symbol, index_item)

        payload = profile.to_dict() if isinstance(profile, StockProfile) else profile
        payload = self._merge_profile_index_fields(payload)
        self.cache.set(cache_key, payload)
        return payload

    def get_stock_profile_index(self) -> dict[str, dict]:
        cached = self.index_cache.get("CN:all:profile_index:v1")
        if isinstance(cached, dict) and cached:
            return cached
        if not hasattr(self.provider, "get_stock_profile_index"):
            return {}
        index = self.provider.get_stock_profile_index()
        if isinstance(index, dict) and index:
            self.index_cache.set("CN:all:profile_index:v1", index)
            return index
        return {}

    def _merge_profile_index_fields(self, payload: dict | None) -> dict | None:
        if not isinstance(payload, dict):
            return payload
        symbol = str(payload.get("symbol") or "").zfill(6)
        if not re.fullmatch(r"\d{6}", symbol):
            return payload
        if not _is_missing_profile_value(payload.get("industry")) and not _is_missing_profile_value(payload.get("listing_date")):
            return payload
        index_item = _find_profile_index_item(self.get_stock_profile_index(), symbol, payload.get("name"))
        if not isinstance(index_item, dict):
            return payload
        merged = dict(payload)
        for key in ("name", "industry", "listing_date", "total_shares", "float_shares", "market_cap", "float_market_cap", "pb"):
            if _is_missing_profile_value(merged.get(key)) and not _is_missing_profile_value(index_item.get(key)):
                merged[key] = index_item[key]
        if "已切换" in str(payload.get("name") or "") and index_item.get("name"):
            merged["name"] = index_item["name"]
        source = str(merged.get("source") or "")
        index_source = str(index_item.get("source") or "A股全量基础资料索引")
        if index_item.get("symbol") and index_item.get("symbol") != symbol:
            index_source = f"{index_source}(现代码{index_item.get('symbol')})"
        if index_source and index_source not in source:
            merged["source"] = f"{source} + {index_source}" if source else index_source
        return merged

    def _profile_from_index_item(self, symbol: str, index_item: dict | None) -> dict | None:
        if not isinstance(index_item, dict):
            return None
        payload = {
            "symbol": symbol,
            "name": index_item.get("name"),
            "market": "CN",
            "industry": index_item.get("industry"),
            "listing_date": index_item.get("listing_date"),
            "latest_price": None,
            "total_shares": index_item.get("total_shares"),
            "float_shares": index_item.get("float_shares"),
            "market_cap": index_item.get("market_cap"),
            "float_market_cap": index_item.get("float_market_cap"),
            "pe_ttm": None,
            "pb": index_item.get("pb"),
            "turnover_rate": None,
            "source": str(index_item.get("source") or "A股全量基础资料索引"),
            "updated_at": None,
        }
        if index_item.get("symbol") and index_item.get("symbol") != symbol:
            payload["source"] = f"{payload['source']}(现代码{index_item.get('symbol')})"
        return payload
