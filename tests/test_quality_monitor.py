import pandas as pd

from quality_monitor import (
    build_backtest_risk_summary,
    build_compare_scorecard,
    build_hot_data_status,
    build_recommendation_explanation,
    build_stock_data_quality_summary,
)


def test_stock_data_quality_flags_missing_extended_info():
    data = pd.DataFrame({"close": [1, 2, 3]})

    summary = build_stock_data_quality_summary(data, quote=None, profile={"market_cap": 1}, extended_info={})

    assert summary["status"] in {"risk", "partial"}
    assert "实时行情缺失，当前价可能使用K线兜底" in summary["issues"]
    assert any("历史K线仅" in item for item in summary["warnings"])


def test_stock_data_quality_explains_failed_fund_flow_source():
    data = pd.DataFrame({"close": list(range(80))})
    extended_info = {
        "financial": {"metrics": {"归母净利润": 1}},
        "fund_flow": {
            "status": "source_failed",
            "source": "东方财富资金流",
            "reason": "远端连接中断",
        },
    }

    summary = build_stock_data_quality_summary(
        data,
        quote={"price": 10},
        profile={"market_cap": 1, "pe_ttm": 10, "pb": 1},
        extended_info=extended_info,
    )

    assert "资金流接口失败：远端连接中断" in summary["warnings"]


def test_compare_scorecard_sorts_without_changing_source_metrics():
    metrics = [
        {"symbol": "A", "name": "弱", "return_20d": -5, "return_60d": -3, "max_drawdown": -30, "volatility": 80},
        {"symbol": "B", "name": "强", "return_20d": 8, "return_60d": 12, "max_drawdown": -8, "volatility": 20, "up_day_ratio": 60, "trend_slope_20d": 1},
    ]

    scorecard = build_compare_scorecard(metrics)

    assert [item["symbol"] for item in scorecard] == ["B", "A"]
    assert scorecard[0]["compare_score"] > scorecard[1]["compare_score"]


def test_backtest_risk_summary_extracts_worst_cases():
    results = [
        {"eval_status": "completed", "outcome": "win", "simulated_return_pct": 5},
        {"eval_status": "completed", "outcome": "loss", "simulated_return_pct": -4, "analysis_date": "2026-05-01"},
        {"eval_status": "insufficient_data", "outcome": None},
    ]

    summary = build_backtest_risk_summary(results)

    assert summary["completed"] == 2
    assert summary["loss_count"] == 1
    assert summary["worst_simulated_return_pct"] == -4
    assert summary["worst_cases"][0]["analysis_date"] == "2026-05-01"


def test_hot_data_status_reports_empty_sections():
    status = build_hot_data_status({"gainers": [{"代码": "000001"}], "losers": []})

    assert status["status"] == "partial"
    assert status["counts"]["gainers"] == 1
    assert status["missing"] == ["losers"]


def test_recommendation_missing_evidence_uses_chinese_labels():
    stock = {
        "symbol": "600000",
        "name": "test",
        "score": 72,
        "latest_price": 10,
        "indicators": {"ma20": 9.5, "boll_lower": 8.8},
    }

    explanation = build_recommendation_explanation(stock, strategy="多因子稳健型")

    assert "扩展信息（财务/资金/公告/风险事件）" in explanation["missing_data"]
    assert "基础资料（行业/市值/估值/换手率）" in explanation["missing_data"]
    assert "extended_info" not in explanation["missing_data"]
    assert "profile" not in explanation["missing_data"]


def test_recommendation_explanation_does_not_promote_failed_strategy_check():
    stock = {
        "symbol": "600000",
        "name": "test",
        "score": 72,
        "latest_price": 10,
        "strategy_checks": {
            "市值<300亿": True,
            "均线金叉+放量": False,
            "财务确认": True,
            "连涨3日": True,
        },
        "strategy_details": {
            "技术说明": "均线满足，量比 0.02 未达 1.2",
            "财务确认": "最新净利润未亏损",
            "连涨3日": "连续3日上涨",
        },
    }

    explanation = build_recommendation_explanation(stock, strategy="多因子稳健型")

    assert "均线满足，量比 0.02 未达 1.2" not in explanation["why_selected"]
    assert any("未通过：均线金叉+放量" in item for item in explanation["risk_flags"])
