"""Stock pool helpers for recommendation strategies."""
from __future__ import annotations

from collections.abc import Iterable
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


def main_board_stocks(stocks: Iterable[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
    result = [stock for stock in stocks if is_main_board(stock.get("code"))]
    return result[:limit] if limit else result


def main_board_sector_stocks(sector_name: str) -> list[dict[str, Any]]:
    return [stock for stock in SECTOR_STOCKS.get(sector_name, []) if is_main_board(stock.get("code"))]


def strategy_sector_stocks(sector_name: str) -> list[dict[str, Any]]:
    return [
        stock
        for stock in SECTOR_STOCKS.get(sector_name, [])
        if is_recommendable_board(stock.get("code")) and "ST" not in str(stock.get("name", "")).upper()
    ]


def merge_strategy_stocks(
    base_stocks: Iterable[dict[str, Any]],
    index_items: Iterable[dict[str, Any]] | None = None,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    merged = {stock["code"]: stock for stock in base_stocks if stock.get("code")}
    for item in index_items or []:
        code = str(item.get("code", "")).strip()
        name = str(item.get("name", "")).strip()
        if code and name:
            merged.setdefault(code, {"code": code, "name": name})
    for code, name in CN_STOCK_NAMES_EXTENDED.items():
        merged.setdefault(code, {"code": code, "name": name})
    result = [
        stock
        for stock in merged.values()
        if is_recommendable_board(stock.get("code")) and "ST" not in str(stock.get("name", "")).upper()
    ]
    return result[:limit] if limit else result
