import pandas as pd

from decision_committee import build_a_share_decision, build_watchlist_decision


def test_a_share_decision_builds_five_agent_views():
    data = pd.DataFrame([{
        "close": 10.5,
        "boll_upper": 12.0,
        "boll_mid": 10.0,
        "boll_lower": 8.0,
        "ma20": 10.0,
        "ma60": 9.5,
    }])
    signals = {
        "recommendation": "偏多信号（强）",
        "macd": "金叉（偏多信号）",
        "rsi": "中性 (55.0)",
        "kdj": "金叉（偏多信号）",
        "boll": "中轨上方，偏多",
    }
    extended = {
        "fund_flow": {
            "main_net_inflow": 12000000,
            "main_net_inflow_ratio": 3.2,
            "five_day_main_net_inflow": 33000000,
            "super_large_net_inflow": 8000000,
        },
        "financial": {"metrics": {
            "营业总收入": 100000000,
            "归母净利润": 20000000,
            "经营现金流量净额": 15000000,
            "每股收益": 0.6,
        }},
        "research": {"reports": [{"title": "测试研报"}], "eps_consensus": {"values": {"2026EPS": 1.2}}},
        "sector_attribution": {
            "industry": {"name": "电力", "change_pct": 1.8},
            "concepts": [{"name": "绿色电力", "change_pct": 2.3}],
        },
        "risk_events": {"announcements": []},
    }
    profile = {"pe_ttm": 18.5, "pb": 1.8, "turnover_rate": 3.5, "market_cap": 20000000000}

    result = build_a_share_decision(data, signals, {"price": 10.6, "change": 1.2}, extended, profile=profile)

    assert result["score"] > 70
    assert result["confidence"] >= 70
    assert result["action"] in ("积极关注", "轻仓试探")
    assert result["position"] in ("2-3成", "1-2成")
    assert result["key_levels"]["support"] == 8.0
    assert len(result["agents"]) == 5
    assert [agent["name"] for agent in result["agents"]] == [
        "技术分析 Agent",
        "资金情绪 Agent",
        "基本面 Agent",
        "题材板块 Agent",
        "风险事件 Agent",
    ]
    assert all("weight" in agent and "confidence" in agent and "raw_score" in agent for agent in result["agents"])
    assert sum(agent["weight"] for agent in result["agents"]) == 100
    assert any("PE" in item for item in result["agents"][2]["evidence"])
    assert result["bullish_points"]
    assert result["catalysts"]


def test_watchlist_decision_penalizes_risk_events():
    item = {
        "symbol": "000001",
        "name": "测试股",
        "price": 10.0,
        "change_pct": -2.0,
        "signal_summary": "偏空信号",
        "indicators": {"boll_upper": 12.0, "boll_mid": 10.0, "boll_lower": 8.0},
    }
    extended = {
        "risk_events": {
            "restricted_release": [{"date": "2026-06-01"}],
            "announcements": [{"title": "股东减持风险提示公告", "type": "风险提示"}],
        }
    }

    result = build_watchlist_decision(item, extended)

    assert result["risk_level"] == "高"
    assert result["action"] == "回避/降仓"
    assert any("风险公告" in risk or "限售解禁" in risk for risk in result["risk_alerts"])
