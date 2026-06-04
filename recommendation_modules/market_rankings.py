"""Market ranking orchestration helpers.

This module keeps hot-market ranking behavior outside ``stock_recommendation``
without changing strategy selection semantics.
"""
from __future__ import annotations

from typing import Any, Protocol


CHANGE_KEYS = ("\u6da8\u8dcc\u5e45",)


class MarketRankingOwner(Protocol):
    def _get_market_ranking_ths(self, sort_asc: bool = False, limit: int = 10, enrich_sector: bool = True) -> list[dict[str, Any]]:
        ...

    def _get_market_ranking_sina(self, sort_asc: bool = False, limit: int = 10, enrich_sector: bool = True) -> list[dict[str, Any]]:
        ...


def get_market_ranking(
    owner: MarketRankingOwner,
    *,
    sort_asc: bool = False,
    limit: int = 10,
    enrich_sector: bool = True,
) -> list[dict[str, Any]]:
    ranking = owner._get_market_ranking_ths(sort_asc=sort_asc, limit=limit, enrich_sector=enrich_sector)
    if ranking:
        return ranking
    return owner._get_market_ranking_sina(sort_asc=sort_asc, limit=limit, enrich_sector=enrich_sector)


def _change_pct(item: dict[str, Any]) -> Any:
    for key in CHANGE_KEYS:
        if key in item:
            return item.get(key)
    return None


def top_gainers(ranking: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return [item for item in ranking if _change_pct(item) is not None and _change_pct(item) > 0][:limit]


def top_losers(ranking: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return [item for item in ranking if _change_pct(item) is not None and _change_pct(item) < 0][:limit]
