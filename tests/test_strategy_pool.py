from recommendation_modules import strategy_pool


def test_board_classification_contracts():
    assert strategy_pool.is_main_board("600519") is True
    assert strategy_pool.is_main_board("000001") is True
    assert strategy_pool.is_main_board("300750") is False
    assert strategy_pool.is_recommendable_board("300750") is True
    assert strategy_pool.is_recommendable_board("688981") is False
    assert strategy_pool.board_label("300750") == "创业板"


def test_main_board_and_strategy_pool_filters():
    stocks = [
        {"code": "600001", "name": "主板A"},
        {"code": "300001", "name": "创业板A"},
        {"code": "688001", "name": "科创板A"},
        {"code": "000001", "name": "ST主板"},
    ]

    main_board = strategy_pool.main_board_stocks(stocks)
    strategy = strategy_pool.merge_strategy_stocks(stocks, [], limit=10)

    assert [item["code"] for item in main_board] == ["600001", "000001"]
    assert "300001" in [item["code"] for item in strategy]
    assert "688001" not in [item["code"] for item in strategy]
    assert "000001" not in [item["code"] for item in strategy]


def test_pool_sources_can_be_injected_without_changing_order():
    sector_stocks = {
        "demo": [
            {"code": "300001", "name": "Growth"},
            {"code": "600001", "name": "Main"},
            {"code": "688001", "name": "Star"},
        ]
    }

    main_board = strategy_pool.main_board_sector_stocks("demo", sector_stocks=sector_stocks)
    strategy = strategy_pool.strategy_sector_stocks("demo", sector_stocks=sector_stocks)
    merged = strategy_pool.merge_strategy_stocks(
        [{"code": "000001", "name": "Base"}],
        [{"code": "300001", "name": "Index"}],
        extended_names={"600001": "Extended"},
    )

    assert [item["code"] for item in main_board] == ["600001"]
    assert [item["code"] for item in strategy] == ["300001", "600001"]
    assert [item["code"] for item in merged] == ["000001", "300001", "600001"]


def test_classic_short_term_candidates_alternate_markets_and_filter_risk_names():
    stocks = [
        {"code": "600001", "name": "Shanghai 1"},
        {"code": "600002", "name": "Shanghai 2"},
        {"code": "000001", "name": "Shenzhen 1"},
        {"code": "000002", "name": "ST Shenzhen"},
        {"code": "000003", "name": "退市股票"},
        {"code": "002001", "name": "Shenzhen 2"},
    ]

    result = strategy_pool.classic_short_term_candidates(stocks, limit=4)

    assert [item["code"] for item in result] == ["600001", "000001", "600002", "002001"]
