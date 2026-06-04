from recommendation_modules import board_rankings


class _Owner:
    def __init__(self):
        self.calls = []
        self.values = {
            "sector_ths": [],
            "sector_em": [],
            "sector_ths_ak": [],
            "concept_ths": [],
            "concept_em": [],
            "concept_ths_ak": [],
        }

    def _get_hot_sectors_ths_html(self, limit=30):
        self.calls.append(("sector_ths", limit))
        return self.values["sector_ths"]

    def _get_hot_sectors_akshare_em(self, limit=30):
        self.calls.append(("sector_em", limit))
        return self.values["sector_em"]

    def _get_hot_sectors_akshare_ths(self, limit=30):
        self.calls.append(("sector_ths_ak", limit))
        return self.values["sector_ths_ak"]

    def _get_hot_concepts_ths_html(self, limit=30):
        self.calls.append(("concept_ths", limit))
        return self.values["concept_ths"]

    def _get_hot_concepts_akshare_em(self, limit=30):
        self.calls.append(("concept_em", limit))
        return self.values["concept_em"]

    def _get_hot_concepts_akshare_ths(self, limit=30):
        self.calls.append(("concept_ths_ak", limit))
        return self.values["concept_ths_ak"]


def test_hot_sectors_prefers_ths():
    owner = _Owner()
    owner.values["sector_ths"] = [{"name": "ths"}, {"name": "extra"}]

    assert board_rankings.hot_sectors(owner, 1) == [{"name": "ths"}]
    assert owner.calls == [("sector_ths", 1)]


def test_hot_concepts_falls_back_to_eastmoney_then_ths_akshare():
    owner = _Owner()
    owner.values["concept_ths_ak"] = [{"name": "ths-ak"}]

    assert board_rankings.hot_concepts(owner, 3) == [{"name": "ths-ak"}]
    assert owner.calls == [("concept_ths", 3), ("concept_em", 3), ("concept_ths_ak", 3)]
