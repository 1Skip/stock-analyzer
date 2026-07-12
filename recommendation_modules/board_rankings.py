"""Board ranking orchestration helpers."""
from __future__ import annotations

from typing import Any, Protocol


class BoardRankingOwner(Protocol):
    def _get_hot_sectors_ths_hotlist(self, limit: int = 30) -> list[dict[str, Any]]:
        ...

    def _get_hot_sectors_wencai(self, limit: int = 30) -> list[dict[str, Any]]:
        ...

    def _get_hot_sectors_ths_html(self, limit: int = 30) -> list[dict[str, Any]]:
        ...

    def _get_hot_sectors_akshare_em(self, limit: int = 30) -> list[dict[str, Any]]:
        ...

    def _get_hot_sectors_sina_industry(self, limit: int = 30) -> list[dict[str, Any]]:
        ...

    def _get_hot_sectors_akshare_ths(self, limit: int = 30) -> list[dict[str, Any]]:
        ...

    def _get_hot_concepts_ths_html(self, limit: int = 30) -> list[dict[str, Any]]:
        ...

    def _get_hot_concepts_ths_hotlist(self, limit: int = 30) -> list[dict[str, Any]]:
        ...

    def _get_hot_concepts_wencai(self, limit: int = 30) -> list[dict[str, Any]]:
        ...

    def _get_hot_concepts_akshare_em(self, limit: int = 30) -> list[dict[str, Any]]:
        ...

    def _get_hot_concepts_akshare_ths(self, limit: int = 30) -> list[dict[str, Any]]:
        ...

    def _get_hot_indices_ths_hotlist(self, limit: int = 30) -> list[dict[str, Any]]:
        ...


def hot_sectors(owner: BoardRankingOwner, limit: int = 30) -> list[dict[str, Any]]:
    sectors = owner._get_hot_sectors_ths_hotlist(limit)
    if sectors:
        return sectors[:limit]
    sectors = owner._get_hot_sectors_wencai(limit)
    if sectors:
        return sectors[:limit]
    sectors = owner._get_hot_sectors_ths_html(limit)
    if sectors:
        return sectors[:limit]
    sectors = owner._get_hot_sectors_akshare_em(limit)
    if sectors:
        return sectors[:limit]
    sectors = owner._get_hot_sectors_sina_industry(limit)
    if sectors:
        return sectors[:limit]
    return owner._get_hot_sectors_akshare_ths(limit)[:limit]


def hot_concepts(owner: BoardRankingOwner, limit: int = 30) -> list[dict[str, Any]]:
    concepts = owner._get_hot_concepts_ths_hotlist(limit)
    if concepts:
        return concepts[:limit]
    concepts = owner._get_hot_concepts_wencai(limit)
    if concepts:
        return concepts[:limit]
    concepts = owner._get_hot_concepts_ths_html(limit)
    if concepts:
        return concepts[:limit]
    concepts = owner._get_hot_concepts_akshare_em(limit)
    if concepts:
        return concepts[:limit]
    return owner._get_hot_concepts_akshare_ths(limit)[:limit]


def hot_indices(owner: BoardRankingOwner, limit: int = 30) -> list[dict[str, Any]]:
    return owner._get_hot_indices_ths_hotlist(limit)[:limit]


def merge_short_term_hot_board_rows(
    sector_rows: list[dict[str, Any]] | None,
    concept_rows: list[dict[str, Any]] | None,
    limit: int = 10,
) -> list[dict[str, str]]:
    rows = []
    seen = set()

    def append_row(item: dict[str, Any]) -> None:
        value = item.get("板块") or item.get("行业") or item.get("概念") or item.get("名称")
        name = str(value or "").strip()
        if not name or name in seen:
            return
        seen.add(name)
        rows.append({
            "name": name,
            "code": str(item.get("代码") or item.get("code") or "").strip(),
            "category": str(item.get("类别") or item.get("category") or "").strip(),
            "leader": str(item.get("领涨股") or item.get("领涨股票") or "").strip(),
        })

    sector_rows = sector_rows or []
    concept_rows = concept_rows or []
    for index in range(max(len(concept_rows), len(sector_rows))):
        if index < len(concept_rows):
            append_row(concept_rows[index])
        if index < len(sector_rows):
            append_row(sector_rows[index])
        if len(rows) >= limit:
            break
    return rows[:limit]
