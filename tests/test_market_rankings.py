from recommendation_modules import market_rankings


class _Owner:
    def __init__(self, ths, sina):
        self.ths = ths
        self.sina = sina
        self.calls = []

    def _get_market_ranking_ths(self, sort_asc=False, limit=10, enrich_sector=True):
        self.calls.append(("ths", sort_asc, limit, enrich_sector))
        return self.ths

    def _get_market_ranking_sina(self, sort_asc=False, limit=10, enrich_sector=True):
        self.calls.append(("sina", sort_asc, limit, enrich_sector))
        return self.sina


def test_get_market_ranking_prefers_ths():
    owner = _Owner(ths=[{"code": "000001"}], sina=[{"code": "000002"}])

    result = market_rankings.get_market_ranking(owner, sort_asc=True, limit=3, enrich_sector=False)

    assert result == [{"code": "000001"}]
    assert owner.calls == [("ths", True, 3, False)]


def test_get_market_ranking_falls_back_to_sina():
    owner = _Owner(ths=[], sina=[{"code": "000002"}])

    result = market_rankings.get_market_ranking(owner, sort_asc=False, limit=5, enrich_sector=True)

    assert result == [{"code": "000002"}]
    assert owner.calls == [("ths", False, 5, True), ("sina", False, 5, True)]


def test_top_gainers_and_losers_filter_without_resorting():
    rows = [
        {"code": "a", "涨跌幅": 2.0},
        {"code": "b", "涨跌幅": 0.0},
        {"code": "c", "涨跌幅": -3.0},
        {"code": "d", "涨跌幅": 1.0},
    ]

    assert [item["code"] for item in market_rankings.top_gainers(rows, 2)] == ["a", "d"]
    assert [item["code"] for item in market_rankings.top_losers(rows, 2)] == ["c"]
