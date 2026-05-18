"""个股扩展信息服务。"""
from __future__ import annotations

import re

from config import (
    CACHE_TTL_STOCK_EXTENDED_INFO,
    CACHE_TTL_STOCK_FINANCIAL,
    CACHE_TTL_STOCK_FUND_FLOW,
    CACHE_TTL_STOCK_RESEARCH,
    CACHE_TTL_STOCK_RISK_EVENTS,
)
from data.cache import JsonFileCache
from data.providers.akshare_info_provider import AkShareInfoProvider


class StockInfoService:
    """财务摘要、资金流、新闻等扩展信息服务。"""

    cache_schema_version = "v5"

    def __init__(self, provider: AkShareInfoProvider | None = None, cache: JsonFileCache | None = None):
        self.provider = provider or AkShareInfoProvider()
        self.cache = cache or JsonFileCache("stock_extended_info", CACHE_TTL_STOCK_EXTENDED_INFO)
        cache_dir = getattr(self.cache, "path", None)
        cache_dir = cache_dir.parent if cache_dir is not None else None
        self.financial_cache = JsonFileCache("stock_financial", CACHE_TTL_STOCK_FINANCIAL, cache_dir=cache_dir)
        self.fund_flow_cache = JsonFileCache("stock_fund_flow", CACHE_TTL_STOCK_FUND_FLOW, cache_dir=cache_dir)
        self.research_cache = JsonFileCache("stock_research", CACHE_TTL_STOCK_RESEARCH, cache_dir=cache_dir)
        self.risk_cache = JsonFileCache("stock_risk_events", CACHE_TTL_STOCK_RISK_EVENTS, cache_dir=cache_dir)

    def get_stock_extended_info(
        self,
        symbol: str,
        market: str = "CN",
        include_deep_layers: bool = True,
    ) -> dict | None:
        symbol = str(symbol or "").strip()
        if market != "CN" or not re.fullmatch(r"\d{6}", symbol):
            return None

        layer_mode = "full" if include_deep_layers else "core"
        cache_key = f"{market}:{symbol}:extended:{self.cache_schema_version}:{layer_mode}"
        cached = self.cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

        layered = self._get_layered_cached_info(symbol, market, include_deep_layers)
        if isinstance(layered, dict):
            self.cache.set(cache_key, layered)
            return layered

        payload = self.provider.get_stock_extended_info(symbol, include_deep_layers=include_deep_layers)
        self._set_layered_cached_info(symbol, market, payload, include_deep_layers)
        if self._has_required_core_layers(payload):
            self.cache.set(cache_key, payload)
        return payload

    def get_cached_stock_extended_info(
        self,
        symbol: str,
        market: str = "CN",
        include_deep_layers: bool = True,
    ) -> dict | None:
        """Return cached extended info only; never call the upstream provider."""
        symbol = str(symbol or "").strip()
        if market != "CN" or not re.fullmatch(r"\d{6}", symbol):
            return None

        layer_mode = "full" if include_deep_layers else "core"
        cache_key = f"{market}:{symbol}:extended:{self.cache_schema_version}:{layer_mode}"
        cached = self.cache.get(cache_key)
        if isinstance(cached, dict):
            return cached
        return self._get_layered_cached_info(symbol, market, include_deep_layers)

    def _get_layered_cached_info(self, symbol: str, market: str, include_deep_layers: bool) -> dict | None:
        base_key = f"{market}:{symbol}"
        financial = self.financial_cache.get(f"{base_key}:financial:v1")
        fund_flow = self.fund_flow_cache.get(f"{base_key}:fund_flow:v1")
        if not self._is_usable_layer(financial) or not self._is_usable_layer(fund_flow):
            return None

        payload = {
            "symbol": symbol,
            "financial": financial,
            "fund_flow": fund_flow,
            "news": [],
            "market_news": [],
            "research": {"reports": [], "eps_consensus": {}},
            "dividend": {},
            "risk_events": {"lhb": {}, "restricted_release": [], "announcements": []},
            "sector_attribution": {"industry": {}, "concepts": []},
            "source": "layered_cache",
        }

        news = self.research_cache.get(f"{base_key}:news:v1")
        market_news = self.research_cache.get(f"{base_key}:market_news:v1")
        if isinstance(news, list):
            payload["news"] = news
        if isinstance(market_news, list):
            payload["market_news"] = market_news

        if include_deep_layers:
            research = self.research_cache.get(f"{base_key}:research:v1")
            dividend = self.research_cache.get(f"{base_key}:dividend:v1")
            sector_attribution = self.research_cache.get(f"{base_key}:sector_attribution:v1")
            risk_events = self.risk_cache.get(f"{base_key}:risk_events:v1")
            if not isinstance(risk_events, dict):
                return None
            if isinstance(research, dict):
                payload["research"] = research
            if isinstance(dividend, dict):
                payload["dividend"] = dividend
            if isinstance(sector_attribution, dict):
                payload["sector_attribution"] = sector_attribution
            payload["risk_events"] = risk_events
        return payload

    def _set_layered_cached_info(self, symbol: str, market: str, payload: dict | None, include_deep_layers: bool) -> None:
        if not isinstance(payload, dict):
            return
        base_key = f"{market}:{symbol}"
        if self._is_usable_layer(payload.get("financial")):
            self.financial_cache.set(f"{base_key}:financial:v1", payload.get("financial"))
        if self._is_usable_layer(payload.get("fund_flow")):
            self.fund_flow_cache.set(f"{base_key}:fund_flow:v1", payload.get("fund_flow"))
        if isinstance(payload.get("news"), list):
            self.research_cache.set(f"{base_key}:news:v1", payload.get("news"))
        if isinstance(payload.get("market_news"), list):
            self.research_cache.set(f"{base_key}:market_news:v1", payload.get("market_news"))
        if not include_deep_layers:
            return
        for field in ("research", "dividend", "sector_attribution"):
            if isinstance(payload.get(field), dict):
                self.research_cache.set(f"{base_key}:{field}:v1", payload.get(field))
        if isinstance(payload.get("risk_events"), dict):
            self.risk_cache.set(f"{base_key}:risk_events:v1", payload.get("risk_events"))

    @staticmethod
    def _is_usable_layer(value: object) -> bool:
        if not isinstance(value, dict) or not value:
            return False
        if value.get("status") in {"source_failed", "source_empty"}:
            return False
        return True

    def _has_required_core_layers(self, payload: dict | None) -> bool:
        if not isinstance(payload, dict):
            return False
        return self._is_usable_layer(payload.get("financial")) and self._is_usable_layer(payload.get("fund_flow"))
