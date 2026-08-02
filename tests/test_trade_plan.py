from trade_plan import build_trade_plan_for_stock, enrich_recommendations_with_trade_plan


def _stock(symbol="002001"):
    return {
        "symbol": symbol,
        "name": "测试股",
        "score": 88,
        "latest_price": 10.0,
        "strategy": "多因子稳健型",
        "indicators": {
            "ma5": 10.1,
            "ma10": 9.9,
            "ma20": 9.5,
            "ma60": 8.8,
            "boll_upper": 11.2,
            "boll_mid": 10.0,
            "boll_lower": 9.0,
        },
    }


def test_build_trade_plan_from_daily_indicators_only():
    plan = build_trade_plan_for_stock(_stock(), strategy="多因子稳健型", sector="全部")

    assert plan["buy_zone"] == "9.00 ~ 9.50"
    assert plan["stop_loss"] == 8.8
    assert plan["take_profit_1"] == 11.2
    assert plan["take_profit_2"] > plan["take_profit_1"]
    assert plan["position"] == "1-2成"
    assert "不使用盘中实时行情" in plan["data_basis"]
    assert "不参与选股" in plan["data_basis"]


def test_enrich_trade_plan_does_not_reorder_or_filter():
    stocks = [_stock("002001"), _stock("002002")]
    original_symbols = [stock["symbol"] for stock in stocks]

    result = enrich_recommendations_with_trade_plan(stocks, strategy="短线", sector="电力")

    assert result is stocks
    assert [stock["symbol"] for stock in result] == original_symbols
    assert all("trade_plan" in stock for stock in result)
    assert result[0]["score"] == 88


def test_trade_plan_includes_risk_announcement_invalid_condition():
    stock = _stock()
    stock["extended_info"] = {
        "risk_events": {
            "announcements": [{"title": "关于股东减持风险提示公告"}],
        }
    }

    plan = build_trade_plan_for_stock(stock, strategy="短线")

    assert any("减持风险" in item for item in plan["invalid_conditions"])


def test_experimental_strategy_uses_its_own_execution_levels():
    stock = _stock()
    stock["strategy"] = "实验策略"
    stock["strategy_execution_levels"] = {
        "buy_zone_low": 9.75,
        "buy_zone_high": 10.15,
        "stop_loss": 9.50,
        "take_profit_1": 10.55,
        "max_holding_days": 5,
        "price_source": "信号日真实前复权日K",
    }

    plan = build_trade_plan_for_stock(stock, strategy="实验策略", sector="全部")

    assert plan["buy_zone_low"] == 9.75
    assert plan["buy_zone_high"] == 10.15
    assert plan["stop_loss"] == 9.5
    assert plan["take_profit_1"] == 10.55
    assert plan["max_holding_days"] == 5
    assert plan["current_action"] == "仅限模拟账户观察"
