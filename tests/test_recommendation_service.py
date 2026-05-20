from recommendation_service import RecommendationService


class FakeCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value


class FakeQuoteService:
    def get_batch_realtime_quotes(self, symbols, market="CN"):
        return {
            symbols[0]: {
                "price": 10.5,
                "change_pct": 2.0,
                "open": 10.2,
                "high": 10.8,
                "low": 10.1,
                "volume": 100000,
                "source": "test realtime",
            }
        } if symbols else {}

    def get_stock_data(self, symbol, period="1y", market="CN", adjust=""):
        import pandas as pd

        self.last_adjust = adjust

        dates = pd.date_range("2025-12-01", periods=80, freq="B")
        close = [10 + index * 0.03 for index in range(len(dates))]
        return pd.DataFrame({
            "date": dates,
            "open": [value - 0.05 for value in close],
            "high": [value + 0.12 for value in close],
            "low": [value - 0.12 for value in close],
            "close": close,
            "volume": [100000 + index * 100 for index in range(len(dates))],
        })


class FakeQuoteServiceWithFuture(FakeQuoteService):
    def get_stock_data(self, symbol, period="1y", market="CN", adjust=""):
        import pandas as pd

        return pd.DataFrame({
            "date": ["2026-05-18", "2026-05-19", "2026-05-20", "2026-05-21", "2026-05-22", "2026-05-25"],
            "open": [9.8, 10.2, 10.5, 10.4, 10.6, 10.8],
            "high": [10.2, 10.8, 11.0, 10.7, 11.1, 11.3],
            "low": [9.7, 10.0, 10.4, 10.1, 10.5, 10.7],
            "close": [10.0, 10.5, 10.8, 10.2, 10.9, 11.0],
            "volume": [100000, 110000, 120000, 115000, 130000, 125000],
        })


class FakeFundamentalService:
    def __init__(self):
        self.called = []

    def get_stock_profile(self, symbol, market="CN"):
        self.called.append((symbol, market))
        return {
            "symbol": symbol,
            "industry": "电子 — 消费电子",
            "market_cap": 12_300_000_000,
            "pe_ttm": 18.6,
            "pb": 2.1,
            "turnover_rate": 3.2,
            "source": "测试基础资料",
        }


class FakeRecommender:
    def __init__(self):
        self.last_aggressive_diagnostics = {"strategy": "激进突破型"}
        self.last_multi_factor_diagnostics = {"strategy": "多因子稳健型"}
        self.called = []

    def get_aggressive_breakout_recommendations(self, num_stocks, progress_callback=None):
        self.called.append(("aggressive", num_stocks, bool(progress_callback)))
        return [_stock("002001", "激进突破型")]

    def get_multi_factor_recommendations(self, num_stocks, progress_callback=None):
        self.called.append(("multi", num_stocks, bool(progress_callback)))
        return [_stock("002002", "多因子稳健型")]


class TwoStockRecommender(FakeRecommender):
    def get_multi_factor_recommendations(self, num_stocks, progress_callback=None):
        self.called.append(("multi", num_stocks, bool(progress_callback)))
        weak = _stock("002010", "多因子稳健型")
        weak.update({"score": 70, "change_pct": 7, "signals": {}, "indicators": {}})
        strong = _stock("002011", "多因子稳健型")
        strong.update({"score": 90, "change_pct": 1, "signals": {"macd": "金叉"}, "indicators": {}})
        return [weak, strong]


def _stock(symbol, strategy):
    return {
        "symbol": symbol,
        "name": "测试股",
        "strategy": strategy,
        "score": 80,
        "rating": "观察候选",
        "latest_price": 10,
        "change_pct": 1,
        "indicators": {},
        "signals": {},
    }


def test_recommendation_service_routes_aggressive_without_changing_strategy():
    recommender = FakeRecommender()
    service = RecommendationService(
        recommender=recommender,
        quote_service=FakeQuoteService(),
        result_cache=FakeCache(),
    )

    result = service.run("激进突破型", "全部", 5, progress_callback=lambda *_: None)

    assert recommender.called == [("aggressive", 5, True)]
    assert result["title"] == "激进突破型"
    assert result["recommended"][0]["latest_price"] == 10.5
    assert result["recommended"][0]["alpha_score"] is not None
    assert result["diagnostics"]["strategy"] == "激进突破型"
    assert result["diagnostics"]["alpha_ranker"]["enabled"] is True
    assert result["diagnostics"]["alpha_ranker"]["sorted"] is False


def test_recommendation_display_indicators_use_analysis_page_context():
    service = RecommendationService(
        recommender=FakeRecommender(),
        quote_service=FakeQuoteService(),
        result_cache=FakeCache(),
    )
    recommended = [_stock("002001", "test")]

    service._refresh_final_quotes(recommended)
    stock = recommended[0]

    assert stock["display_indicator_context"]["period"] == "1y"
    assert stock["display_indicator_context"]["adjust"] == "qfq"
    assert stock["display_indicator_context"]["realtime_merged"] is False
    assert service.quote_service.last_adjust == "qfq"
    assert stock["indicators"]["ma30"] > 0
    assert stock["indicators"] != {}


def test_recommendation_service_fills_display_profile_without_changing_strategy():
    fundamentals = FakeFundamentalService()
    service = RecommendationService(
        recommender=FakeRecommender(),
        quote_service=FakeQuoteService(),
        fundamental_service=fundamentals,
        result_cache=FakeCache(),
    )
    recommended = [_stock("002001", "test")]

    service._refresh_final_quotes(recommended)
    stock = recommended[0]

    assert fundamentals.called == [("002001", "CN")]
    assert stock["profile"]["industry"] == "电子 — 消费电子"
    assert stock["profile"]["market_cap"] == 12_300_000_000
    assert stock["latest_price"] == 10.5


def test_recommendation_service_ignores_invalid_zero_realtime_quote():
    class BadQuoteService(FakeQuoteService):
        def get_batch_realtime_quotes(self, symbols, market="CN"):
            return {symbols[0]: {"price": 0, "change_pct": -100, "source": "bad quote"}} if symbols else {}

    service = RecommendationService(
        recommender=FakeRecommender(),
        quote_service=BadQuoteService(),
        fundamental_service=FakeFundamentalService(),
        result_cache=FakeCache(),
    )
    recommended = [_stock("002001", "test")]

    service._refresh_final_quotes(recommended)
    stock = recommended[0]

    assert stock["latest_price"] == 10
    assert stock["change_pct"] == 1


def test_recommendation_service_persists_latest_result():
    cache = FakeCache()
    service = RecommendationService(
        recommender=FakeRecommender(),
        quote_service=FakeQuoteService(),
        result_cache=cache,
    )

    result = service.run("多因子稳健型", "全部", 5)
    latest = service.latest("多因子稳健型", "全部", 5)

    assert latest == result
    assert latest["title"] == "多因子稳健型"


def test_observability_does_not_change_strategy_selected_order(monkeypatch):
    import recommendation_service as module

    monkeypatch.setattr(module, "RECOMMEND_RANKER_SORT", False)
    service = module.RecommendationService(
        recommender=TwoStockRecommender(),
        quote_service=FakeQuoteService(),
        result_cache=FakeCache(),
    )

    result = service.run("多因子稳健型", "全部", 5)

    assert [stock["symbol"] for stock in result["recommended"]] == ["002010", "002011"]
    assert all("explanation" in stock for stock in result["recommended"])
    assert all("trade_plan" in stock for stock in result["recommended"])
    assert result["diagnostics"]["quality"]["stock_count"] == 2


def test_trade_plan_is_added_after_selection_without_changing_order():
    service = RecommendationService(
        recommender=TwoStockRecommender(),
        quote_service=FakeQuoteService(),
        result_cache=FakeCache(),
    )

    result = service.run("多因子稳健型", "全部", 5)

    assert [stock["symbol"] for stock in result["recommended"]] == ["002010", "002011"]
    plan = result["recommended"][0]["trade_plan"]
    assert plan["buy_zone"]
    assert plan["stop_loss"] is not None
    assert "不使用盘中实时行情" in plan["data_basis"]
    assert "不参与选股" in plan["data_basis"]


def test_recommendation_service_sorts_alpha_only_when_config_enabled(monkeypatch):
    import recommendation_service as module

    monkeypatch.setattr(module, "RECOMMEND_RANKER_SORT", True)
    service = module.RecommendationService(
        recommender=TwoStockRecommender(),
        quote_service=FakeQuoteService(),
        result_cache=FakeCache(),
    )

    result = service.run("多因子稳健型", "全部", 5)

    assert result["recommended"][0]["symbol"] == "002011"
    assert result["diagnostics"]["alpha_ranker"]["sorted"] is True


def test_recommendation_service_persists_t1_plan_without_changing_strategy(monkeypatch):
    cache = FakeCache()
    recommender = FakeRecommender()
    service = RecommendationService(
        recommender=recommender,
        quote_service=FakeQuoteService(),
        result_cache=cache,
    )
    service.plan_cache = FakeCache()

    plan = service.run_t1_plan("激进突破型", "全部", 5)
    latest = service.latest_t1_plan("激进突破型", "全部", 5)

    assert recommender.called == [("aggressive", 5, False)]
    assert latest["recommended"] == plan["recommended"]
    assert plan["mode"] == "T+1_PLAN"
    assert plan["recommended"][0]["symbol"] == "002001"
    assert plan["data_status"]["realtime_check"] == "not_checked"
    assert plan["generation_metrics"]["realtime_used_for_selection"] is False
    assert plan["generation_metrics"]["scan_scope_changed"] is False
    assert plan["history_key"]


def test_t1_plan_history_is_saved_and_read_only():
    recommender = FakeRecommender()
    service = RecommendationService(
        recommender=recommender,
        quote_service=FakeQuoteServiceWithFuture(),
        result_cache=FakeCache(),
    )
    service.plan_cache = FakeCache()
    service.plan_history_cache = FakeCache()

    plan = service.run_t1_plan("多因子稳健型", "全部", 5)
    history = service.list_t1_plan_history(strategy="多因子稳健型", sector="全部")
    review = service.evaluate_t1_plan_history(strategy="多因子稳健型", sector="全部")

    assert recommender.called == [("multi", 5, False)]
    assert len(history) == 1
    assert history[0]["recommended_symbols"] == [plan["recommended"][0]["symbol"]]
    assert review["summary"]["plans"] == 1
    assert review["summary"]["completed_items"] == 1
    assert recommender.called == [("multi", 5, False)]


def test_t1_plan_records_preheat_and_elapsed_metrics_without_changing_strategy(monkeypatch):
    cache = FakeCache()
    recommender = FakeRecommender()
    service = RecommendationService(
        recommender=recommender,
        quote_service=FakeQuoteService(),
        result_cache=cache,
    )
    service.plan_cache = FakeCache()
    monkeypatch.setattr(service, "_preheat_kline_cache", lambda: {"status": "ok", "total": 2, "refreshed": 2, "failed": 0})
    monkeypatch.setattr(service, "_preheat_extended_info_cache", lambda recommended: {"status": "ok", "total": len(recommended), "refreshed": len(recommended), "failed": 0})

    plan = service.run_t1_plan(
        "多因子稳健型",
        "全部",
        5,
        trigger="scheduler",
        preheat_kline=True,
        preheat_extended_info=True,
    )

    assert recommender.called == [("multi", 5, False)]
    assert plan["generation_metrics"]["trigger"] == "scheduler"
    assert plan["generation_metrics"]["elapsed_ms"] >= 0
    assert plan["data_status"]["preheat"]["kline_cache"]["status"] == "ok"
    assert plan["data_status"]["preheat"]["extended_info_cache"]["status"] == "ok"


def test_preheat_extended_info_cache_is_shallow_and_bounded(monkeypatch):
    import data.services.info_service as info_module
    import recommendation_service as module

    calls = []

    class FakeInfoService:
        def get_stock_extended_info(self, symbol, market, include_deep_layers=False):
            calls.append((symbol, market, include_deep_layers))
            return {"symbol": symbol}

    monkeypatch.setattr(module, "T1_PLAN_PREHEAT_EXTENDED_INFO_MAX_SYMBOLS", 2)
    monkeypatch.setattr(module, "T1_PLAN_PREHEAT_EXTENDED_INFO_TIMEOUT_SECONDS", 20)
    monkeypatch.setattr(module, "T1_PLAN_PREHEAT_EXTENDED_INFO_DEEP", False)
    monkeypatch.setattr(info_module, "StockInfoService", FakeInfoService)
    service = module.RecommendationService(
        recommender=FakeRecommender(),
        quote_service=FakeQuoteService(),
        result_cache=FakeCache(),
    )

    result = service._preheat_extended_info_cache([
        {"symbol": "002001"},
        {"symbol": "002002"},
        {"symbol": "002003"},
    ])

    assert calls == [("002001", "CN", False), ("002002", "CN", False)]
    assert result["status"] == "partial"
    assert result["attempted"] == 2
    assert result["refreshed"] == 2
    assert result["skipped"] == 1
    assert result["deep_layers"] is False


def test_preheat_extended_info_cache_stops_on_timeout(monkeypatch):
    import data.services.info_service as info_module
    import recommendation_service as module

    calls = []

    class FakeInfoService:
        def get_stock_extended_info(self, symbol, market, include_deep_layers=False):
            calls.append(symbol)
            return {"symbol": symbol}

    tick = {"value": 0}

    def fake_perf_counter():
        tick["value"] += 25
        return tick["value"]

    monkeypatch.setattr(module, "T1_PLAN_PREHEAT_EXTENDED_INFO_MAX_SYMBOLS", 5)
    monkeypatch.setattr(module, "T1_PLAN_PREHEAT_EXTENDED_INFO_TIMEOUT_SECONDS", 20)
    monkeypatch.setattr(info_module, "StockInfoService", FakeInfoService)
    monkeypatch.setattr(module.time, "perf_counter", fake_perf_counter)
    service = module.RecommendationService(
        recommender=FakeRecommender(),
        quote_service=FakeQuoteService(),
        result_cache=FakeCache(),
    )

    result = service._preheat_extended_info_cache([
        {"symbol": "002001"},
        {"symbol": "002002"},
    ])

    assert calls == []
    assert result["status"] == "timeout"
    assert result["attempted"] == 0
    assert result["skipped"] == 2


def test_latest_t1_plan_marks_cache_source():
    service = RecommendationService(
        recommender=FakeRecommender(),
        quote_service=FakeQuoteService(),
        result_cache=FakeCache(),
    )
    service.plan_cache = FakeCache()
    service.plan_cache.set(
        "CN:多因子稳健型:全部:5:T1",
        {"mode": "T+1_PLAN", "strategy": "多因子稳健型", "sector": "全部", "num_stocks": 5, "data_status": {}},
    )

    latest = service.latest_t1_plan("多因子稳健型", "全部", 5)

    assert latest["data_status"]["source"] == "t1_plan_cache"

    assert "cache_read_metrics" in latest["data_status"]
    assert latest["data_status"]["cache_read_metrics"]["elapsed_ms"] >= 0
    assert latest["data_status"]["cache_read_metrics"]["realtime_used_for_selection"] is False
    assert latest["data_status"]["cache_read_metrics"]["scan_scope_changed"] is False


def test_entry_check_uses_eastmoney_quotes_without_re_picking(monkeypatch):
    recommender = FakeRecommender()
    service = RecommendationService(
        recommender=recommender,
        quote_service=FakeQuoteService(),
        result_cache=FakeCache(),
    )
    plan = {
        "recommended": [_stock("002001", "激进突破型")],
    }

    monkeypatch.setattr(
        "recommendation_service._fetch_eastmoney_realtime_quotes",
        lambda symbols: {"002001": {"price": 10.2, "change_pct": 1.2, "source": "东方财富实时行情"}},
    )

    result = service.check_entry_plan(plan)

    assert recommender.called == []
    assert result["status"] == "ok"
    assert result["items"][0]["symbol"] == "002001"
    assert result["items"][0]["status"] == "可按计划观察"
    assert result["source"] == "东方财富实时行情"


def test_entry_check_falls_back_to_sina_after_eastmoney_failure(monkeypatch):
    recommender = FakeRecommender()
    service = RecommendationService(
        recommender=recommender,
        quote_service=FakeQuoteService(),
        result_cache=FakeCache(),
    )
    plan = {
        "recommended": [_stock("002001", "激进突破型")],
    }
    monkeypatch.setattr("recommendation_service._fetch_eastmoney_realtime_quotes", lambda symbols: {})
    monkeypatch.setattr("recommendation_service._fetch_tencent_realtime_quotes", lambda symbols: {})

    result = service.check_entry_plan(plan)

    assert recommender.called == []
    assert result["status"] == "ok"
    assert result["source"] == "新浪财经"
    assert result["items"][0]["latest_price"] == 10.5


def test_entry_check_falls_back_to_tencent_after_eastmoney_and_sina_failure(monkeypatch):
    class EmptyQuoteService:
        def get_batch_realtime_quotes(self, symbols, market="CN"):
            return {}

    service = RecommendationService(
        recommender=FakeRecommender(),
        quote_service=EmptyQuoteService(),
        result_cache=FakeCache(),
    )
    plan = {
        "recommended": [_stock("002001", "激进突破型")],
    }
    monkeypatch.setattr("recommendation_service._fetch_eastmoney_realtime_quotes", lambda symbols: {})
    monkeypatch.setattr(
        "recommendation_service._fetch_tencent_realtime_quotes",
        lambda symbols: {"002001": {"price": 10.4, "change_pct": 1.8, "source": "腾讯行情"}},
    )

    result = service.check_entry_plan(plan)

    assert result["status"] == "ok"
    assert result["source"] == "腾讯行情"
    assert result["items"][0]["latest_price"] == 10.4


def test_entry_check_reports_all_realtime_sources_unavailable(monkeypatch):
    class EmptyQuoteService:
        def get_batch_realtime_quotes(self, symbols, market="CN"):
            return {}

    service = RecommendationService(
        recommender=FakeRecommender(),
        quote_service=EmptyQuoteService(),
        result_cache=FakeCache(),
    )
    plan = {
        "recommended": [_stock("002001", "激进突破型")],
    }
    monkeypatch.setattr("recommendation_service._fetch_eastmoney_realtime_quotes", lambda symbols: {})
    monkeypatch.setattr("recommendation_service._fetch_tencent_realtime_quotes", lambda symbols: {})

    result = service.check_entry_plan(plan)

    assert result["status"] == "realtime_unavailable"
    assert result["source"] == "全部实时源失败"
    assert "实时行情不可用" in result["message"]



def test_entry_check_pauses_st_stock_without_re_picking(monkeypatch):
    recommender = FakeRecommender()
    service = RecommendationService(
        recommender=recommender,
        quote_service=FakeQuoteService(),
        result_cache=FakeCache(),
    )
    stock = _stock("002001", "多因子稳健型")
    stock["name"] = "ST测试"
    plan = {"recommended": [stock]}
    monkeypatch.setattr(
        "recommendation_service._fetch_eastmoney_realtime_quotes",
        lambda symbols: {"002001": {"price": 10.2, "change_pct": 1.2, "volume": 1000}},
    )

    result = service.check_entry_plan(plan)

    assert recommender.called == []
    assert result["items"][0]["status"] == "暂缓入场"
    assert "ST" in result["items"][0]["reason"]


def test_entry_check_waits_when_open_gap_is_too_high(monkeypatch):
    service = RecommendationService(
        recommender=FakeRecommender(),
        quote_service=FakeQuoteService(),
        result_cache=FakeCache(),
    )
    plan = {"recommended": [_stock("002001", "多因子稳健型")]}
    monkeypatch.setattr(
        "recommendation_service._fetch_eastmoney_realtime_quotes",
        lambda symbols: {"002001": {"price": 10.8, "change_pct": 3.0, "open": 10.6, "prev_close": 10.0, "volume": 1000}},
    )

    result = service.check_entry_plan(plan)

    assert result["items"][0]["status"] == "等待回落"
    assert "高开" in result["items"][0]["reason"]


def test_entry_check_pauses_when_price_breaks_boll_support(monkeypatch):
    service = RecommendationService(
        recommender=FakeRecommender(),
        quote_service=FakeQuoteService(),
        result_cache=FakeCache(),
    )
    stock = _stock("002001", "多因子稳健型")
    stock["indicators"] = {"boll_lower": 9.5}
    plan = {"recommended": [stock]}
    monkeypatch.setattr(
        "recommendation_service._fetch_eastmoney_realtime_quotes",
        lambda symbols: {"002001": {"price": 9.2, "change_pct": -2.0, "volume": 1000}},
    )

    result = service.check_entry_plan(plan)

    assert result["items"][0]["status"] == "暂缓入场"
    assert "BOLL" in result["items"][0]["reason"]


def test_entry_check_pauses_on_risk_announcement_without_changing_list(monkeypatch):
    recommender = FakeRecommender()
    service = RecommendationService(
        recommender=recommender,
        quote_service=FakeQuoteService(),
        result_cache=FakeCache(),
    )
    stock = _stock("002001", "多因子稳健型")
    stock["extended_info"] = {
        "risk_events": {"announcements": [{"title": "关于股东减持风险提示公告"}]}
    }
    plan = {"recommended": [stock]}
    monkeypatch.setattr(
        "recommendation_service._fetch_eastmoney_realtime_quotes",
        lambda symbols: {"002001": {"price": 10.2, "change_pct": 1.2, "volume": 1000}},
    )

    result = service.check_entry_plan(plan)

    assert recommender.called == []
    assert [item["symbol"] for item in result["items"]] == ["002001"]
    assert result["items"][0]["status"] == "暂缓入场"
    assert "风险公告" in result["items"][0]["reason"]


def test_entry_check_pauses_when_quote_looks_suspended(monkeypatch):
    service = RecommendationService(
        recommender=FakeRecommender(),
        quote_service=FakeQuoteService(),
        result_cache=FakeCache(),
    )
    plan = {"recommended": [_stock("002001", "多因子稳健型")]}
    monkeypatch.setattr(
        "recommendation_service._fetch_eastmoney_realtime_quotes",
        lambda symbols: {"002001": {"price": 10.0, "change_pct": 0.0, "open": 10.0, "high": 10.0, "low": 10.0, "volume": 0}},
    )

    result = service.check_entry_plan(plan)

    assert result["items"][0]["status"] == "暂缓入场"
    assert "停牌" in result["items"][0]["reason"] or "交易" in result["items"][0]["reason"]
