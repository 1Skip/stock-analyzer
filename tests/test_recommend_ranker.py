from recommend_ranker import enrich_recommendations_with_alpha, score_recommendation_alpha


def test_alpha_ranker_adds_explainable_fields():
    stock = {
        "symbol": "002001",
        "name": "测试股",
        "score": 82,
        "rating": "多因子共振",
        "change_pct": 2.0,
        "indicators": {"ma5": 12, "ma10": 11, "ma20": 10, "ma60": 9},
        "signals": {"macd": "金叉", "kdj": "金叉"},
        "strategy_checks": {"均线金叉+放量": True, "财务确认": True, "连涨3日": True},
        "strategy_details": {"量比": 1.8},
        "extended_info": {
            "fund_flow": {"five_day_main_net_inflow": 50_000_000, "main_net_inflow": 10_000_000},
            "financial": {"metrics": {"归母净利润": 10_000_000, "净利润同比": 25}},
            "risk_events": {"announcements": []},
        },
        "profile": {"pe_ttm": 25, "pb": 2.0},
    }

    result = score_recommendation_alpha(stock, strategy="多因子稳健型", sector="全部")

    assert result["alpha_score"] > 75
    assert result["alpha_grade"] in {"A", "A+"}
    assert result["rank_reason"]
    assert result["rank_components"]["strategy"] > 0
    assert result["ranker_version"] == "alpha_v1"


def test_alpha_ranker_can_enrich_without_sorting():
    low_alpha_first = [
        {"symbol": "A", "score": 70, "change_pct": 7, "signals": {}, "indicators": {}},
        {"symbol": "B", "score": 90, "change_pct": 1, "signals": {"macd": "金叉"}, "indicators": {}},
    ]

    result = enrich_recommendations_with_alpha(low_alpha_first, sort=False)

    assert [item["symbol"] for item in result] == ["A", "B"]
    assert all("alpha_score" in item for item in result)


def test_alpha_ranker_sorts_when_enabled():
    low_alpha_first = [
        {"symbol": "A", "score": 70, "change_pct": 7, "signals": {}, "indicators": {}},
        {"symbol": "B", "score": 90, "change_pct": 1, "signals": {"macd": "金叉"}, "indicators": {}},
    ]

    result = enrich_recommendations_with_alpha(low_alpha_first, sort=True)

    assert result[0]["symbol"] == "B"
