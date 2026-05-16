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
            symbols[0]: {"price": 10.5, "change_pct": 2.0}
        } if symbols else {}


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

    def get_all_sector_recommendations(self, short_top_n=None, long_top_n=None):
        return {"测试板块": {"激进突破型": [_stock("002003", "激进突破型")]}}


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
    assert result["diagnostics"] == {"strategy": "激进突破型"}


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
