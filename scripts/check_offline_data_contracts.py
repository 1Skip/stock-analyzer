"""Offline data contract checks.

This script validates result shapes and missing-data states only. It does not
fetch network data, write caches, or create synthetic market prices.
"""
from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


OHLCV_COLUMNS = {"open", "high", "low", "close", "volume"}
QUOTE_FIELDS = {"symbol", "name", "price", "prev_close"}
INDEX_QUOTE_FIELDS = {"symbol", "name", "price", "change_pct", "prev_close"}


def _fail(message: str) -> None:
    raise AssertionError(message)


def validate_kline_contract(data: pd.DataFrame | None) -> str:
    if data is None:
        return "missing"
    missing = OHLCV_COLUMNS - set(data.columns)
    if missing:
        _fail(f"kline missing columns: {sorted(missing)}")
    return "available" if not data.empty else "empty"


def validate_quote_contract(quote: dict | None) -> str:
    if quote is None:
        return "missing"
    missing = QUOTE_FIELDS - set(quote)
    if missing:
        _fail(f"quote missing fields: {sorted(missing)}")
    return "available" if quote.get("price") is not None else "missing"


def validate_index_quote_contract(quote: dict | None) -> str:
    if quote is None:
        return "missing"
    missing = INDEX_QUOTE_FIELDS - set(quote)
    if missing:
        _fail(f"index quote missing fields: {sorted(missing)}")
    return "available" if quote.get("price") is not None else "missing"


def validate_stock_profile_contract() -> dict:
    from data.models import StockProfile

    profile = StockProfile(symbol="000000", name=None, market="CN", source="offline-contract")
    payload = profile.to_dict()
    expected_fields = {field.name for field in fields(StockProfile)}
    missing = expected_fields - set(payload)
    if missing:
        _fail(f"profile missing fields: {sorted(missing)}")
    restored = StockProfile.from_dict(payload)
    if restored != profile:
        _fail("profile round-trip changed values")
    return payload


def run_checks() -> dict:
    empty_kline = pd.DataFrame(columns=sorted(OHLCV_COLUMNS))
    unavailable_quote = {
        "symbol": "000000",
        "name": None,
        "price": None,
        "prev_close": None,
    }
    unavailable_index_quote = {
        "symbol": "000000",
        "name": None,
        "price": None,
        "change_pct": None,
        "prev_close": None,
    }
    profile = validate_stock_profile_contract()
    return {
        "kline_status": validate_kline_contract(empty_kline),
        "quote_status": validate_quote_contract(unavailable_quote),
        "index_quote_status": validate_index_quote_contract(unavailable_index_quote),
        "profile_fields": sorted(profile),
    }


def main() -> int:
    result = run_checks()
    print("offline data contracts passed")
    print(f"kline={result['kline_status']}")
    print(f"quote={result['quote_status']}")
    print(f"index_quote={result['index_quote_status']}")
    print(f"profile_fields={len(result['profile_fields'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
