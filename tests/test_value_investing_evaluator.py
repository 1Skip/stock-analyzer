from value_investing_evaluator import build_value_investing_snapshot


def _profile(**overrides):
    profile = {
        "industry": "消费电子",
        "listing_date": "2010-01-01",
        "total_shares": 100_000_000,
        "pe_ttm": 10,
        "pb": 1.8,
        "source": "真实基础资料",
    }
    profile.update(overrides)
    return profile


def _extended(**overrides):
    payload = {
        "financial": {
            "period": "20251231",
            "source": "真实财务摘要",
            "metrics": {
                "营业总收入": 1_000_000_000,
                "归母净利润": 100_000_000,
                "经营现金流量净额": 120_000_000,
                "每股收益": 1.0,
            },
            "history": [
                {"period": "20241231", "归母净利润": 90_000_000},
                {"period": "20251231", "归母净利润": 100_000_000},
            ],
        },
        "research": {"eps_consensus": {"values": {"2026预测每股收益": 1.1}}},
        "dividend": {"cash_dividend_per_share": 0.25},
        "source": "真实扩展资料",
    }
    payload.update(overrides)
    return payload


def test_value_snapshot_is_screen_grade_and_separates_scenarios():
    result = build_value_investing_snapshot(
        _profile(),
        _extended(),
        current_price=8.0,
        price_as_of="2026-07-22",
        price_source="真实行情",
    )

    assert result["status"] == "ok"
    assert result["grade"] == "screen-grade"
    assert [row["key"] for row in result["scenarios"]] == ["downside", "base", "upside"]
    assert result["current_price"] == 8.0
    assert result["facts"]["annualized_net_profit"] == 100_000_000
    assert result["facts"]["annualized_operating_cash_flow"] == 120_000_000
    assert result["base_value_per_share"] > 0
    assert "资本开支" in result["missing_evidence"]
    assert {item["name"] for item in result["pillars"]} == {"芒格质量", "巴菲特价值", "Codex证据纪律"}


def test_value_snapshot_annualizes_partial_period_without_hiding_assumption():
    extended = _extended()
    extended["financial"]["period"] = "20260331"
    extended["financial"]["metrics"]["归母净利润"] = 25_000_000
    extended["financial"]["metrics"]["经营现金流量净额"] = 20_000_000
    extended["financial"]["metrics"]["每股收益"] = 0.25

    result = build_value_investing_snapshot(_profile(), extended, current_price=8, price_as_of="2026-07-22")

    assert result["assumptions"]["annualization_factor"] == 4.0
    assert result["facts"]["annualized_net_profit"] == 100_000_000


def test_value_snapshot_rejects_missing_price_and_financial_industry():
    no_price = build_value_investing_snapshot(_profile(), _extended(), current_price=None)
    financial = build_value_investing_snapshot(
        _profile(industry="银行"),
        _extended(),
        current_price=8,
    )

    assert no_price["status"] == "not_evaluable"
    assert financial["status"] == "not_evaluable"
    assert "专用模型" in financial["message"]


def test_value_snapshot_does_not_invent_value_without_positive_earnings_or_cash():
    extended = _extended()
    extended["financial"]["metrics"].update({
        "归母净利润": -10,
        "经营现金流量净额": -20,
        "每股收益": -0.1,
    })

    result = build_value_investing_snapshot(_profile(), extended, current_price=8)

    assert result["status"] == "not_evaluable"
    assert "正向盈利" in result["missing_evidence"]
