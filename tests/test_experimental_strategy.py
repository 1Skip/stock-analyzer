from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from experimental_strategy import (
    EXPERIMENTAL_RULE_ID,
    EXPERIMENTAL_STRATEGY_VERSION,
    build_market_regime_snapshot,
    build_price_candidate,
    build_experimental_candidate,
    build_experimental_validation_gate,
    evaluate_experimental_technical,
    select_experimental_universe,
)
from stock_recommendation import StockRecommender


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


def _display_indicators():
    return {
        "macd": 0.2,
        "macd_signal": 0.1,
        "macd_hist": 0.2,
        "rsi": 42.0,
        "rsi_6": 42.0,
        "rsi_12": 48.0,
        "rsi_24": 52.0,
        "kdj_k": 45.0,
        "kdj_d": 40.0,
        "kdj_j": 55.0,
        "boll_upper": 10.8,
        "boll_mid": 10.0,
        "boll_lower": 9.2,
        "ma5": 9.9,
        "ma10": 9.8,
        "ma20": 10.0,
        "ma30": 9.8,
        "ma60": 9.5,
    }


def test_market_regime_requires_broad_participation_and_keeps_cash_when_weak():
    strong = [
        {
            "evaluation": {
                "metrics": {
                    "close": 10.5,
                    "ma20": 10.0,
                    "ma60": 9.5,
                    "return_20d": 0.05,
                }
            }
        }
        for _ in range(500)
    ]
    weak = [
        {
            "evaluation": {
                "metrics": {
                    "close": 9.0,
                    "ma20": 10.0,
                    "ma60": 10.5,
                    "return_20d": -0.05,
                }
            }
        }
        for _ in range(500)
    ]

    assert build_market_regime_snapshot(strong)["status"] == "risk_on"
    cash = build_market_regime_snapshot(weak)
    assert cash["passed"] is False
    assert cash["status"] == "cash"


def test_market_regime_uses_recent_complete_trade_date_when_latest_is_partial():
    older = [
        {
            "evaluation": {
                "as_of_date": "2026-07-23",
                "metrics": {
                    "close": 10.5,
                    "ma20": 10.0,
                    "ma60": 9.5,
                    "return_20d": 0.05,
                },
            }
        }
        for _ in range(500)
    ]
    latest = [
        {
            "evaluation": {
                "as_of_date": "2026-07-24",
                "metrics": {
                    "close": 9.0,
                    "ma20": 10.0,
                    "ma60": 10.5,
                    "return_20d": -0.05,
                },
            }
        }
        for _ in range(20)
    ]

    result = build_market_regime_snapshot([*older, *latest])

    assert result["as_of_date"] == "2026-07-23"
    assert result["latest_available_date"] == "2026-07-24"
    assert result["latest_date_stocks"] == 20
    assert result["date_fallback_used"] is True
    assert result["stocks"] == 500
    assert result["stale_or_other_date_stocks"] == 20
    assert result["status"] == "risk_on"


def test_market_regime_keeps_latest_date_and_cash_when_no_date_has_full_coverage():
    older = [
        {
            "evaluation": {
                "as_of_date": "2026-07-23",
                "metrics": {
                    "close": 10.5,
                    "ma20": 10.0,
                    "ma60": 9.5,
                    "return_20d": 0.05,
                },
            }
        }
        for _ in range(400)
    ]
    latest = [
        {
            "evaluation": {
                "as_of_date": "2026-07-24",
                "metrics": {
                    "close": 9.0,
                    "ma20": 10.0,
                    "ma60": 10.5,
                    "return_20d": -0.05,
                },
            }
        }
        for _ in range(20)
    ]

    result = build_market_regime_snapshot([*older, *latest])

    assert result["as_of_date"] == "2026-07-24"
    assert result["latest_available_date"] == "2026-07-24"
    assert result["latest_date_stocks"] == 20
    assert result["date_fallback_used"] is False
    assert result["stocks"] == 20
    assert result["stale_or_other_date_stocks"] == 400
    assert result["status"] == "cash"


def test_v2_candidate_requires_complete_real_display_indicators_and_has_execution_levels():
    evaluation = {
        "passed": True,
        "score": 72.5,
        "checks": {"候选规则": True},
        "metrics": {
            "close": 10.0,
            "ma5": 9.9,
            "ma10": 9.8,
            "ma20": 10.0,
            "ma60": 9.5,
            "return_1d": 0.01,
            "return_3d": -0.03,
            "return_60d": 0.10,
            "volatility_20d": 0.02,
            "rsi_2": 20.0,
            "rsi_6": 42.0,
            "boll_upper": 10.8,
            "boll_mid": 10.0,
            "boll_lower": 9.2,
        },
        "display_indicators": _display_indicators(),
    }

    candidate = build_price_candidate({"code": "600001", "name": "测试股"}, evaluation)

    assert candidate["strategy_version"] == EXPERIMENTAL_STRATEGY_VERSION
    assert candidate["strategy_rule_id"] == EXPERIMENTAL_RULE_ID
    assert candidate["indicators"]["macd_signal"] == 0.1
    assert candidate["indicators"]["kdj_k"] == 45.0
    assert candidate["indicators"]["boll_mid"] == 10.0
    assert candidate["indicators"]["ma30"] == 9.8
    assert candidate["strategy_execution_levels"]["max_holding_days"] == 5
    assert candidate["strategy_execution_levels"]["buy_zone_low"] > 0

    missing = {**evaluation, "display_indicators": {**_display_indicators(), "macd_signal": None}}
    assert build_price_candidate({"code": "600001", "name": "测试股"}, missing) is None


def test_production_experimental_route_keeps_cash_when_market_breadth_is_weak(monkeypatch):
    stocks = [{"code": f"600{index:03d}", "name": f"测试股{index}"} for index in range(500)]
    recommender = StockRecommender()
    monkeypatch.setattr(recommender, "_get_strategy_popular_cn_stocks", lambda: stocks)
    monkeypatch.setattr(
        recommender,
        "_analyze_experimental_technical",
        lambda stock, market="CN", fetcher=None, rule_id=EXPERIMENTAL_RULE_ID: {
            "stock": stock,
            "evaluation": {
                "passed": False,
                "metrics": {
                    "close": 9.0,
                    "ma20": 10.0,
                    "ma60": 10.5,
                    "return_20d": -0.05,
                },
            },
        },
    )

    assert recommender.get_experimental_recommendations(5) == []
    assert recommender.last_experimental_diagnostics["status"] == "cash_regime"
    assert recommender.last_experimental_diagnostics["market_regime"]["status"] == "cash"


def test_production_experimental_route_stays_cash_when_rotation_has_no_rule(
    monkeypatch,
):
    recommender = StockRecommender()
    monkeypatch.setattr(
        "stock_recommendation.resolve_experimental_strategy_selection",
        lambda: {
            "status": "cash",
            "rule_id": None,
            "strategy_version": None,
            "reason": "没有合格候选",
        },
    )

    assert recommender.get_experimental_recommendations(5) == []
    assert recommender.last_experimental_diagnostics["status"] == "strategy_paused"


def test_production_experimental_route_builds_candidate_only_in_risk_on_market(monkeypatch):
    stocks = [{"code": f"600{index:03d}", "name": f"测试股{index}"} for index in range(500)]
    recommender = StockRecommender()
    monkeypatch.setattr(recommender, "_get_strategy_popular_cn_stocks", lambda: stocks)

    def analyze(
        stock,
        market="CN",
        fetcher=None,
        rule_id=EXPERIMENTAL_RULE_ID,
    ):
        index = int(stock["code"][-3:])
        return {
            "stock": stock,
            "evaluation": {
                "passed": index == 0,
                "score": 72.5,
                "checks": {"候选规则": index == 0},
                "metrics": {
                    "close": 10.5,
                    "ma5": 10.3,
                    "ma10": 10.1,
                    "ma20": 10.0,
                    "ma60": 9.5,
                    "return_1d": 0.01,
                    "return_3d": -0.03,
                    "return_20d": 0.05,
                    "return_60d": 0.10,
                    "volatility_20d": 0.02,
                    "rsi_2": 20.0,
                    "rsi_6": 42.0,
                    "boll_upper": 10.8,
                    "boll_mid": 10.0,
                    "boll_lower": 9.2,
                },
                "display_indicators": _display_indicators(),
            },
        }

    monkeypatch.setattr(recommender, "_analyze_experimental_technical", analyze)

    result = recommender.get_experimental_recommendations(5)

    assert [item["symbol"] for item in result] == ["600000"]
    assert recommender.last_experimental_diagnostics["market_regime"]["status"] == "risk_on"
