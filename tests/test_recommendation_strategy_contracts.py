"""Recommendation strategy route contracts.

These tests protect the current strategy entry behavior before splitting
``stock_recommendation.py`` into smaller modules. They mock data inputs and
analysis outputs so the tests verify routing, sorting, and result shape without
changing or exercising real selection semantics.
"""

from types import SimpleNamespace

import stock_recommendation as recommendation_module
from recommendation_modules import strategy_pool
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


def test_stock_recommender_keeps_pool_helper_compatibility(monkeypatch):
    recommender = StockRecommender()
    monkeypatch.setattr(strategy_pool, "is_main_board", lambda code: code == "main")
    monkeypatch.setattr(strategy_pool, "is_recommendable_board", lambda code: code == "allowed")
    monkeypatch.setattr(strategy_pool, "board_label", lambda code: f"board:{code}")

    assert recommender._is_main_board("main") is True
    assert recommender._is_main_board("other") is False
    assert recommender._is_recommendable_board("allowed") is True
    assert recommender._board_label("300001") == "board:300001"


def test_stock_pool_wrappers_respect_overridden_predicates(monkeypatch):
    recommender = StockRecommender()
    pool = [
        {"code": "600001", "name": "Main"},
        {"code": "300001", "name": "Growth"},
        {"code": "688001", "name": "Chip"},
    ]
    monkeypatch.setattr(recommendation_module, "get_popular_cn_stocks", lambda: pool)
    monkeypatch.setattr(recommendation_module, "CN_STOCK_NAMES_EXTENDED", {})
    monkeypatch.setattr(
        recommendation_module.StockDataFetcher,
        "_load_stock_name_index",
        lambda max_age_hours=48: [],
    )

    monkeypatch.setattr(recommender, "_is_main_board", lambda code: code == "300001")
    assert [item["code"] for item in recommender._get_main_board_popular_cn_stocks()] == ["300001"]

    monkeypatch.setattr(recommender, "_is_recommendable_board", lambda code: code == "688001")
    assert [item["code"] for item in recommender._get_strategy_popular_cn_stocks()] == ["688001"]


def test_board_constituent_fallback_records_source_diagnostics(monkeypatch, tmp_path):
    from data.cache import JsonFileCache

    recommender = StockRecommender()
    recommender._board_ranking_cache = JsonFileCache(
        "board_rankings_contract_constituents",
        86400,
        cache_dir=tmp_path,
    )

    def industry_source(symbol):
        raise RuntimeError("industry unavailable")

    fake_ak = SimpleNamespace(
        stock_board_industry_cons_em=industry_source,
        stock_board_concept_cons_em=lambda symbol: "concept-result",
    )
    monkeypatch.setattr(recommendation_module, "ak", fake_ak)
    monkeypatch.setattr(recommender, "_get_ths_board_constituent_stocks", lambda *args, **kwargs: [])
    monkeypatch.setattr(recommendation_module.hot_stocks, "_call_without_proxy_env", lambda fetcher: fetcher())
    monkeypatch.setattr(recommendation_module, "run_with_timeout", lambda fetcher, timeout: fetcher())
    monkeypatch.setattr(
        recommender,
        "_normalize_board_constituents",
        lambda value: [{"code": "000001", "name": "Demo"}] if value == "concept-result" else [],
    )

    result = recommender._get_board_constituent_stocks("demo")
    diagnostics = recommender.last_board_ranking_diagnostics["board_constituents:demo"]

    assert result == [{"code": "000001", "name": "Demo"}]
    assert diagnostics["status"] == "fresh"
    assert diagnostics["source"] == "东方财富概念板块成分"
    assert diagnostics["fallback_errors"] == ["东方财富行业板块成分: RuntimeError"]


def test_short_term_hot_board_diagnostics_keep_successful_fallback(monkeypatch, tmp_path):
    from data.cache import JsonFileCache

    recommender = StockRecommender()
    recommender._board_ranking_cache = JsonFileCache(
        "board_rankings_contract_hot_boards",
        86400,
        cache_dir=tmp_path,
    )
    monkeypatch.setattr(recommender, "get_hot_sectors_cn", lambda limit: (_ for _ in ()).throw(RuntimeError()))
    monkeypatch.setattr(
        recommender,
        "get_hot_concepts_cn",
        lambda limit: [{"板块": "机器人", "代码": "301024", "类别": "概念"}],
    )

    result = recommender._get_short_term_hot_board_rows(limit=3)
    diagnostics = recommender.last_board_ranking_diagnostics["short_term_hot_boards"]

    assert [item["name"] for item in result] == ["机器人"]
    assert diagnostics["status"] == "fresh"
    assert diagnostics["source_counts"] == {"industry": 0, "concept": 1}
    assert diagnostics["fallback_errors"] == ["行业板块: RuntimeError"]


def test_short_term_same_input_same_output_contract(monkeypatch):
    recommender = StockRecommender()
    calls = []
    stocks = [
        {**_stock("000001", "A"), "short_term_sectors": ["苹果概念"]},
        {**_stock("000002", "B"), "short_term_sectors": ["苹果概念"]},
        {**_stock("000003", "C"), "short_term_sectors": ["特斯拉概念"]},
    ]
    scores = {"000001": 80, "000002": 95, "000003": 70}
    monkeypatch.setattr(recommender, "_get_short_term_all_candidate_stocks", lambda limit: stocks)
    monkeypatch.setattr(recommender, "_get_short_term_hot_board_rows", lambda limit: [])
    monkeypatch.setattr(recommender, "_short_term_technical_filter_passes", lambda analysis: True)
    monkeypatch.setattr(recommender, "_short_term_all_pattern_filter_passes", lambda analysis: True)

    def analyze(code, market="CN"):
        calls.append((code, market))
        return _result(code, scores[code])

    monkeypatch.setattr(recommender, "_analyze_short_term", analyze)

    result = recommender.get_short_term_recommendations(2)

    assert sorted(calls) == [("000001", "CN"), ("000002", "CN"), ("000003", "CN")]
    assert _snapshot(result) == [("000002", 95, "B"), ("000001", 80, "A")]


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

    def run_strategy_pool(
        strategy,
        stocks,
        num_stocks,
        analyzer,
        progress_callback=None,
        progress_stage=None,
        max_workers=None,
    ):
        assert strategy == "多因子稳健型"
        assert stocks == shortlist
        assert num_stocks == 2
        assert progress_stage == "深度检查"
        assert max_workers > 5
        return expected

    monkeypatch.setattr(recommender, "_shortlist_multi_factor_candidates", shortlist_candidates)
    monkeypatch.setattr(recommender, "_run_strategy_pool", run_strategy_pool)

    result = recommender.get_multi_factor_recommendations(2)

    assert result == expected
    assert recommender.last_multi_factor_diagnostics["strategy"] == "多因子稳健型"
    assert recommender.last_multi_factor_diagnostics["deep_checked"] == 2
