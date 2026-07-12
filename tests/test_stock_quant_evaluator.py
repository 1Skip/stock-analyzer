import pandas as pd

from stock_quant_evaluator import (
    _select_non_overlapping_matches,
    _volatility_pct,
    _wilson_interval,
    build_stock_quant_snapshot,
)
from technical_indicators import TechnicalIndicators


def _make_trending_data(rows=140):
    prices = [10 + index * 0.06 for index in range(rows)]
    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=rows, freq="B"),
        "open": [price - 0.03 for price in prices],
        "high": [price + 0.12 for price in prices],
        "low": [price - 0.12 for price in prices],
        "close": prices,
        "volume": [100000 + (index % 8) * 5000 for index in range(rows)],
    })


def test_stock_quant_snapshot_scores_single_stock_without_fetching_data():
    data = TechnicalIndicators.calculate_all(_make_trending_data())

    snapshot = build_stock_quant_snapshot(data)

    assert snapshot["status"] == "ok"
    assert snapshot["version"] == "stock_quant_v1"
    assert 0 <= snapshot["score"] <= 100
    assert snapshot["rating"] in {"强势", "偏强", "中性", "偏弱", "弱势"}
    assert {item["name"] for item in snapshot["dimensions"]} == {
        "趋势结构",
        "动量强弱",
        "量能配合",
        "位置结构",
        "风险控制",
    }
    assert snapshot["key_levels"]["support"] is not None
    assert snapshot["similar_pattern"]["match_rule"] in {"趋势+RSI+BOLL+量能", "趋势+RSI+BOLL"}
    assert snapshot["similar_pattern"]["sample_method"] == "non_overlapping_forward_windows"
    assert snapshot["similar_pattern"]["sample_count"] <= snapshot["similar_pattern"]["raw_sample_count"]
    assert snapshot["similar_pattern"]["reliability"]["level"] in {"insufficient", "low", "medium", "high"}
    assert snapshot["calibration"]["status"] == "rule_based_uncalibrated"
    assert snapshot["calibration"]["affects_recommendation"] is False
    assert snapshot["data_basis"].startswith("基于个股分析页当前日K")


def test_stock_quant_snapshot_reports_insufficient_data():
    data = TechnicalIndicators.calculate_all(_make_trending_data(rows=20))

    snapshot = build_stock_quant_snapshot(data)

    assert snapshot["status"] == "insufficient_data"
    assert snapshot["data_rows"] == 20


def test_similar_pattern_matches_use_non_overlapping_forward_windows():
    assert _select_non_overlapping_matches([60, 61, 62, 65, 66, 72], 5) == [60, 65, 72]


def test_wilson_interval_contains_observed_win_rate():
    values = [1.0, 2.0, -1.0, 3.0, -0.5]

    low, high = _wilson_interval(values)

    assert low < 60 < high
    assert 0 <= low <= high <= 100


def test_volatility_pct_uses_daily_not_annualized_scale():
    prices = [100.0]
    for index in range(30):
        prices.append(prices[-1] * (1.01 if index % 2 == 0 else 0.99))

    volatility = _volatility_pct(pd.DataFrame({"close": prices}), 20)

    assert volatility is not None
    assert 0.9 <= volatility <= 1.1
