from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from experimental_strategy import (
    build_experimental_candidate,
    build_experimental_validation_gate,
    evaluate_experimental_technical,
    select_experimental_universe,
)


def test_experimental_universe_is_independent_mature_main_board_only():
    stocks = [
        {"code": "600001", "name": "沪市老股"},
        {"code": "000001", "name": "深市老股"},
        {"code": "300001", "name": "创业板股"},
        {"code": "600002", "name": "ST风险"},
        {"code": "002001", "name": "新上市"},
    ]
    index = {
        "600001": {"listing_date": "2000-01-01"},
        "000001": {"listing_date": "2001-01-01"},
        "300001": {"listing_date": "2010-01-01"},
        "600002": {"listing_date": "2000-01-01"},
        "002001": {"listing_date": (datetime.now() - timedelta(days=300)).date().isoformat()},
    }

    result = select_experimental_universe(stocks, index, limit=10, as_of="2026-07-22")

    assert [item["code"] for item in result] == ["600001", "000001"]


def test_experimental_technical_uses_stable_real_kline_conditions():
    dates = pd.date_range("2025-01-01", periods=140, freq="B")
    x = np.arange(len(dates))
    close = 10 + x * 0.018 + np.sin(x / 4) * 0.18
    data = pd.DataFrame({
        "open": close - 0.03,
        "high": close + 0.10,
        "low": close - 0.10,
        "close": close,
        "volume": np.full(len(dates), 1_000_000.0),
    }, index=dates)

    result = evaluate_experimental_technical(data)

    assert result["passed"] is True
    assert all(result["checks"].values())


def test_experimental_candidate_requires_value_margin_and_positive_cash():
    latest = pd.Series({"close": 8, "macd": 0.2, "macd_signal": 0.1, "macd_hist": 0.1, "rsi": 55, "rsi_6": 55})
    technical = {
        "passed": True,
        "score": 90,
        "latest": latest,
        "checks": {"趋势": True},
        "metrics": {"volatility_20d_pct": 2.0},
        "reason": "通过",
    }
    valuation = {
        "status": "ok",
        "score": 75,
        "grade_label": "筛选级",
        "base_value_per_share": 10,
        "base_margin_of_safety_pct": 25,
        "facts": {"annualized_net_profit": 100, "annualized_operating_cash_flow": 120},
    }

    result = build_experimental_candidate(
        {"code": "600001", "name": "测试股"},
        technical,
        valuation,
    )

    assert result["strategy"] == "实验策略"
    assert result["rating"] == "实验观察候选"
    assert result["score"] == 81.0
    assert build_experimental_candidate(
        {"code": "600001", "name": "测试股"},
        technical,
        {**valuation, "base_margin_of_safety_pct": 5},
    ) is None


def test_experimental_gate_collects_promotes_and_rejects_by_real_samples():
    collecting = build_experimental_validation_gate({"samples_1d": 20, "wins_1d": 12})
    promotable = build_experimental_validation_gate({
        "samples_1d": 200,
        "wins_1d": 120,
        "win_rate_1d_pct": 60,
        "avg_1d_return_pct": 0.8,
        "distinct_plan_dates": 30,
    })
    rejected = build_experimental_validation_gate({
        "samples_1d": 40,
        "wins_1d": 16,
        "win_rate_1d_pct": 40,
        "avg_1d_return_pct": -0.2,
        "distinct_plan_dates": 10,
    })

    assert collecting["status"] == "collecting"
    assert promotable["status"] == "promotable"
    assert rejected["status"] == "rejected"
