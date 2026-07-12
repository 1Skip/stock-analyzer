"""Stock pool helpers for recommendation strategies."""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from stock_names import CN_STOCK_NAMES_EXTENDED, SECTOR_STOCKS


def is_main_board(code: Any) -> bool:
    return str(code).startswith((
        "600", "601", "603", "605",
        "000", "001", "002", "003",
    ))


def is_recommendable_board(code: Any) -> bool:
    return str(code).startswith((
        "600", "601", "603", "605",
        "000", "001", "002", "003",
        "300", "301",
    ))


def board_label(code: Any) -> str:
    code = str(code)
    if code.startswith(("300", "301")):
        return "创业板"
    if code.startswith("6"):
        return "沪市主板"
    return "深市主板"


def main_board_stocks(
    stocks: Iterable[dict[str, Any]],
    limit: int | None = None,
    *,
    predicate: Callable[[Any], bool] | None = None,
) -> list[dict[str, Any]]:
    checker = predicate or is_main_board
    result = [stock for stock in stocks if checker(stock.get("code"))]
    return result[:limit] if limit else result


def classic_short_term_candidates(
    stocks: Iterable[dict[str, Any]],
    limit: int | None = 80,
) -> list[dict[str, Any]]:
    eligible = []
    for stock in stocks:
        code = str(stock.get("code") or "").strip()
        name = str(stock.get("name") or "").strip()
        if not code or not name or "ST" in name.upper() or "退" in name:
            continue
        eligible.append(stock)

    shanghai = [stock for stock in eligible if str(stock.get("code") or "").startswith("6")]
    shenzhen = [stock for stock in eligible if not str(stock.get("code") or "").startswith("6")]
    selected = []
    positions = [0, 0]
    buckets = [shanghai, shenzhen]
    target = len(eligible) if limit is None else max(0, int(limit))
    while len(selected) < target and any(positions[index] < len(bucket) for index, bucket in enumerate(buckets)):
        for index, bucket in enumerate(buckets):
            if positions[index] >= len(bucket):
                continue
            selected.append(bucket[positions[index]])
            positions[index] += 1
            if len(selected) >= target:
                break
    return selected


def main_board_sector_stocks(
    sector_name: str,
    sector_stocks: Mapping[str, Iterable[dict[str, Any]]] | None = None,
    *,
    predicate: Callable[[Any], bool] | None = None,
) -> list[dict[str, Any]]:
    pools = SECTOR_STOCKS if sector_stocks is None else sector_stocks
    checker = predicate or is_main_board
    return [stock for stock in pools.get(sector_name, []) if checker(stock.get("code"))]


def strategy_sector_stocks(
    sector_name: str,
    sector_stocks: Mapping[str, Iterable[dict[str, Any]]] | None = None,
    *,
    predicate: Callable[[Any], bool] | None = None,
) -> list[dict[str, Any]]:
    pools = SECTOR_STOCKS if sector_stocks is None else sector_stocks
    checker = predicate or is_recommendable_board
    return [
        stock
        for stock in pools.get(sector_name, [])
        if checker(stock.get("code")) and "ST" not in str(stock.get("name", "")).upper()
    ]


def merge_strategy_stocks(
    base_stocks: Iterable[dict[str, Any]],
    index_items: Iterable[dict[str, Any]] | None = None,
    *,
    limit: int | None = None,
    extended_names: Mapping[str, str] | None = None,
    predicate: Callable[[Any], bool] | None = None,
) -> list[dict[str, Any]]:
    merged = {stock["code"]: stock for stock in base_stocks if stock.get("code")}
    for item in index_items or []:
        code = str(item.get("code", "")).strip()
        name = str(item.get("name", "")).strip()
        if code and name:
            merged.setdefault(code, {"code": code, "name": name})
    names = CN_STOCK_NAMES_EXTENDED if extended_names is None else extended_names
    for code, name in names.items():
        merged.setdefault(code, {"code": code, "name": name})
    checker = predicate or is_recommendable_board
    result = [
        stock
        for stock in merged.values()
        if checker(stock.get("code")) and "ST" not in str(stock.get("name", "")).upper()
    ]
    return result[:limit] if limit else result
