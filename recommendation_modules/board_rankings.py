"""Board ranking orchestration helpers."""
from __future__ import annotations

from typing import Any, Protocol


class BoardRankingOwner(Protocol):
    def _get_hot_sectors_ths_html(self, limit: int = 30) -> list[dict[str, Any]]:
        ...

    def _get_hot_sectors_akshare_em(self, limit: int = 30) -> list[dict[str, Any]]:
        ...

    def _get_hot_sectors_akshare_ths(self, limit: int = 30) -> list[dict[str, Any]]:
        ...

    def _get_hot_concepts_ths_html(self, limit: int = 30) -> list[dict[str, Any]]:
        ...

    def _get_hot_concepts_akshare_em(self, limit: int = 30) -> list[dict[str, Any]]:
        ...

    def _get_hot_concepts_akshare_ths(self, limit: int = 30) -> list[dict[str, Any]]:
        ...


def hot_sectors(owner: BoardRankingOwner, limit: int = 30) -> list[dict[str, Any]]:
    sectors = owner._get_hot_sectors_ths_html(limit)
    if sectors:
        return sectors[:limit]
    sectors = owner._get_hot_sectors_akshare_em(limit)
    if sectors:
        return sectors[:limit]
    return owner._get_hot_sectors_akshare_ths(limit)[:limit]


def hot_concepts(owner: BoardRankingOwner, limit: int = 30) -> list[dict[str, Any]]:
    concepts = owner._get_hot_concepts_ths_html(limit)
    if concepts:
        return concepts[:limit]
    concepts = owner._get_hot_concepts_akshare_em(limit)
    if concepts:
        return concepts[:limit]
    return owner._get_hot_concepts_akshare_ths(limit)[:limit]
