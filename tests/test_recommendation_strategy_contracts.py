"""Recommendation strategy route contracts.

These tests protect the current strategy entry behavior before splitting
``stock_recommendation.py`` into smaller modules. They mock data inputs and
analysis outputs so the tests verify routing, sorting, and result shape without
changing or exercising real selection semantics.
"""

from stock_recommendation import StockRecommender


def _stock(code, name=None):
    return {"code": code, "name": name or f"Stock {code}"}


def _result(symbol, score):
    return {
        "symbol": symbol,
        "score": score,
        "latest_price": 10.0 + score / 100,
        "change_pct": 1.0,
        "signals": {},
        "indicators": {},
    }


def _snapshot(items):
    return [(item.get("symbol"), item.get("score"), item.get("name")) for item in items]


def test_short_term_same_input_same_output_contract(monkeypatch):
    recommender = StockRecommender()
    calls = []
    stocks = [_stock("000001", "A"), _stock("000002", "B"), _stock("000003", "C")]
    scores = {"000001": 80, "000002": 95, "000003": 70}
    monkeypatch.setattr(recommender, "_get_main_board_popular_cn_stocks", lambda limit: stocks)

    def analyze(code, market="CN"):
        calls.append((code, market))
        return _result(code, scores[code])

    monkeypatch.setattr(recommender, "_analyze_short_term", analyze)

    result = recommender.get_short_term_recommendations(2)

    assert sorted(calls) == [("000001", "CN"), ("000002", "CN"), ("000003", "CN")]
    assert _snapshot(result) == [("000002", 95, "B"), ("000001", 80, "A")]


def test_long_term_same_input_same_output_contract(monkeypatch):
    recommender = StockRecommender()
    calls = []
    stocks = [_stock("600001", "L1"), _stock("600002", "L2"), _stock("600003", "L3")]
    scores = {"600001": 68, "600002": 88, "600003": 77}
    monkeypatch.setattr(recommender, "_get_main_board_popular_cn_stocks", lambda limit: stocks)

    def analyze(code, market="CN"):
        calls.append((code, market))
        return _result(code, scores[code])

    monkeypatch.setattr(recommender, "_analyze_long_term", analyze)

    result = recommender.get_long_term_recommendations(2)

    assert sorted(calls) == [("600001", "CN"), ("600002", "CN"), ("600003", "CN")]
    assert _snapshot(result) == [("600002", 88, "L2"), ("600003", 77, "L3")]


def test_aggressive_breakout_same_input_same_output_contract(monkeypatch):
    recommender = StockRecommender()
    stocks = [_stock("300001"), _stock("000001")]
    expected = [_result("300001", 91), _result("000001", 82)]
    monkeypatch.setattr(recommender, "_get_strategy_popular_cn_stocks", lambda: stocks)

    def run_pool(pool, num_stocks, diagnostics=None, progress_callback=None, **kwargs):
        assert pool == stocks
        assert num_stocks == 2
        assert diagnostics == {"strategy": "激进突破型"}
        assert progress_callback is None
        return expected

    monkeypatch.setattr(recommender, "_run_aggressive_breakout_pool", run_pool)

    result = recommender.get_aggressive_breakout_recommendations(2)

    assert result == expected
    assert recommender.last_aggressive_diagnostics == {"strategy": "激进突破型"}


def test_multi_factor_same_input_same_output_contract(monkeypatch):
    recommender = StockRecommender()
    pool = [_stock("300010"), _stock("002010"), _stock("000010")]
    shortlist = [pool[1], pool[2]]
    expected = [_result("002010", 90), _result("000010", 75)]
    monkeypatch.setattr(recommender, "_get_strategy_popular_cn_stocks", lambda: pool)

    def shortlist_candidates(stocks, num_stocks, diagnostics=None, progress_callback=None, **kwargs):
        assert stocks == pool
        assert num_stocks == 2
        diagnostics["shortlisted"] = len(shortlist)
        return shortlist

    def run_strategy_pool(strategy, stocks, num_stocks, analyzer, progress_callback=None, progress_stage=None):
        assert strategy == "多因子稳健型"
        assert stocks == shortlist
        assert num_stocks == 2
        assert progress_stage == "深度检查"
        return expected

    monkeypatch.setattr(recommender, "_shortlist_multi_factor_candidates", shortlist_candidates)
    monkeypatch.setattr(recommender, "_run_strategy_pool", run_strategy_pool)

    result = recommender.get_multi_factor_recommendations(2)

    assert result == expected
    assert recommender.last_multi_factor_diagnostics["strategy"] == "多因子稳健型"
    assert recommender.last_multi_factor_diagnostics["deep_checked"] == 2
