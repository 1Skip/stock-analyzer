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
