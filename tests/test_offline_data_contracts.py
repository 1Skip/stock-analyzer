import pandas as pd
import pytest

from scripts.check_offline_data_contracts import (
    validate_index_quote_contract,
    validate_kline_contract,
    validate_quote_contract,
    validate_stock_profile_contract,
)


def test_offline_contracts_accept_missing_real_data_states():
    empty_kline = pd.DataFrame(columns=["close", "high", "low", "open", "volume"])
    quote = {"symbol": "000000", "name": None, "price": None, "prev_close": None}
    index_quote = {
        "symbol": "000000",
        "name": None,
        "price": None,
        "change_pct": None,
        "prev_close": None,
    }

    assert validate_kline_contract(empty_kline) == "empty"
    assert validate_quote_contract(quote) == "missing"
    assert validate_index_quote_contract(index_quote) == "missing"


def test_offline_contracts_reject_broken_shapes():
    with pytest.raises(AssertionError, match="kline missing columns"):
        validate_kline_contract(pd.DataFrame(columns=["close"]))

    with pytest.raises(AssertionError, match="quote missing fields"):
        validate_quote_contract({"symbol": "000000"})

    with pytest.raises(AssertionError, match="index quote missing fields"):
        validate_index_quote_contract({"symbol": "000000"})


def test_stock_profile_contract_round_trip_preserves_fields():
    payload = validate_stock_profile_contract()

    assert payload["symbol"] == "000000"
    assert payload["market"] == "CN"
    assert "updated_at" in payload
