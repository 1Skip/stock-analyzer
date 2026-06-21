from recommendation_modules import board_rankings


class _Owner:
    def __init__(self):
        self.calls = []
        self.values = {
            "sector_hotlist": [],
            "sector_ths": [],
            "sector_wencai": [],
            "sector_em": [],
            "sector_sina": [],
            "sector_ths_ak": [],
            "concept_hotlist": [],
            "concept_wencai": [],
            "concept_ths": [],
            "concept_em": [],
            "concept_ths_ak": [],
            "index_hotlist": [],
        }

    def _get_hot_sectors_ths_hotlist(self, limit=30):
        self.calls.append(("sector_hotlist", limit))
        return self.values["sector_hotlist"]

    def _get_hot_sectors_ths_html(self, limit=30):
        self.calls.append(("sector_ths", limit))
        return self.values["sector_ths"]

    def _get_hot_sectors_wencai(self, limit=30):
        self.calls.append(("sector_wencai", limit))
        return self.values["sector_wencai"]

    def _get_hot_sectors_akshare_em(self, limit=30):
        self.calls.append(("sector_em", limit))
        return self.values["sector_em"]

    def _get_hot_sectors_sina_industry(self, limit=30):
        self.calls.append(("sector_sina", limit))
        return self.values["sector_sina"]

    def _get_hot_sectors_akshare_ths(self, limit=30):
        self.calls.append(("sector_ths_ak", limit))
        return self.values["sector_ths_ak"]

    def _get_hot_concepts_ths_html(self, limit=30):
        self.calls.append(("concept_ths", limit))
        return self.values["concept_ths"]

    def _get_hot_concepts_ths_hotlist(self, limit=30):
        self.calls.append(("concept_hotlist", limit))
        return self.values["concept_hotlist"]

    def _get_hot_concepts_wencai(self, limit=30):
        self.calls.append(("concept_wencai", limit))
        return self.values["concept_wencai"]

    def _get_hot_concepts_akshare_em(self, limit=30):
        self.calls.append(("concept_em", limit))
        return self.values["concept_em"]

    def _get_hot_concepts_akshare_ths(self, limit=30):
        self.calls.append(("concept_ths_ak", limit))
        return self.values["concept_ths_ak"]

    def _get_hot_indices_ths_hotlist(self, limit=30):
        self.calls.append(("index_hotlist", limit))
        return self.values["index_hotlist"]


def test_hot_sectors_prefers_ths_hotlist():
    owner = _Owner()
    owner.values["sector_hotlist"] = [{"name": "hotlist"}, {"name": "extra"}]
    owner.values["sector_wencai"] = [{"name": "wencai"}]

    assert board_rankings.hot_sectors(owner, 1) == [{"name": "hotlist"}]
    assert owner.calls == [("sector_hotlist", 1)]


def test_hot_sectors_falls_back_to_ths_html():
    owner = _Owner()
    owner.values["sector_ths"] = [{"name": "ths"}, {"name": "extra"}]

    assert board_rankings.hot_sectors(owner, 1) == [{"name": "ths"}]
    assert owner.calls == [("sector_hotlist", 1), ("sector_wencai", 1), ("sector_ths", 1)]


def test_hot_sectors_prefers_wencai():
    owner = _Owner()
    owner.values["sector_wencai"] = [{"name": "wencai"}]
    owner.values["sector_ths"] = [{"name": "ths"}]

    assert board_rankings.hot_sectors(owner, 1) == [{"name": "wencai"}]
    assert owner.calls == [("sector_hotlist", 1), ("sector_wencai", 1)]


def test_hot_concepts_falls_back_to_eastmoney_then_ths_akshare():
    owner = _Owner()
    owner.values["concept_ths_ak"] = [{"name": "ths-ak"}]

    assert board_rankings.hot_concepts(owner, 3) == [{"name": "ths-ak"}]
    assert owner.calls == [("concept_hotlist", 3), ("concept_wencai", 3), ("concept_ths", 3), ("concept_em", 3), ("concept_ths_ak", 3)]


def test_hot_concepts_prefers_ths_hotlist():
    owner = _Owner()
    owner.values["concept_hotlist"] = [{"name": "hotlist"}]
    owner.values["concept_wencai"] = [{"name": "wencai"}]

    assert board_rankings.hot_concepts(owner, 3) == [{"name": "hotlist"}]
    assert owner.calls == [("concept_hotlist", 3)]


def test_hot_concepts_falls_back_to_wencai():
    owner = _Owner()
    owner.values["concept_wencai"] = [{"name": "wencai"}]
    owner.values["concept_ths"] = [{"name": "ths"}]

    assert board_rankings.hot_concepts(owner, 3) == [{"name": "wencai"}]
    assert owner.calls == [("concept_hotlist", 3), ("concept_wencai", 3)]


def test_hot_sectors_falls_back_to_sina_before_ths_akshare():
    owner = _Owner()
    owner.values["sector_sina"] = [{"name": "sina"}]
    owner.values["sector_ths_ak"] = [{"name": "ths-ak"}]

    assert board_rankings.hot_sectors(owner, 3) == [{"name": "sina"}]
    assert owner.calls == [("sector_hotlist", 3), ("sector_wencai", 3), ("sector_ths", 3), ("sector_em", 3), ("sector_sina", 3)]


def test_hot_indices_uses_ths_hotlist():
    owner = _Owner()
    owner.values["index_hotlist"] = [{"name": "index"}, {"name": "extra"}]

    assert board_rankings.hot_indices(owner, 1) == [{"name": "index"}]
    assert owner.calls == [("index_hotlist", 1)]
