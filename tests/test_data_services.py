"""分层数据服务测试。"""
import pandas as pd

from data.cache import JsonFileCache
from data.health import SourceHealthRegistry
from data.providers.akshare_provider import AkShareProvider
from data.services.fundamental_service import FundamentalDataService


class TestAkShareProvider:

    def test_normalize_stock_profile(self):
        provider = AkShareProvider()
        df = pd.DataFrame([
            {"item": "最新", "value": 11.25},
            {"item": "股票代码", "value": "000001"},
            {"item": "股票简称", "value": "平安银行"},
            {"item": "总股本", "value": 19405918198.0},
            {"item": "流通股", "value": 19405600653.0},
            {"item": "总市值", "value": 218316579727.5},
            {"item": "流通市值", "value": 218313007346.25},
            {"item": "行业", "value": "银行Ⅱ"},
            {"item": "上市时间", "value": 19910403},
        ])

        profile = provider._normalize_stock_profile("000001", df)

        assert profile.symbol == "000001"
        assert profile.name == "平安银行"
        assert profile.industry == "银行Ⅱ"
        assert profile.listing_date == "1991-04-03"
        assert profile.market_cap == 218316579727.5
        assert profile.source == "AKShare/东方财富"

    def test_enrich_valuation_from_tencent(self, monkeypatch):
        provider = AkShareProvider()
        parts = [""] * 47
        parts[1] = "平安银行"
        parts[2] = "000001"
        parts[3] = "11.25"
        parts[38] = "0.53"
        parts[39] = "5.07"
        parts[44] = "2183.13"
        parts[45] = "2183.17"
        parts[46] = "0.47"

        class FakeResponse:
            status_code = 200
            text = "~".join(parts)

        monkeypatch.setattr("data.providers.akshare_provider.requests.get", lambda *args, **kwargs: FakeResponse())

        profile = provider._normalize_stock_profile("000001", pd.DataFrame([
            {"item": "股票代码", "value": "000001"},
            {"item": "股票简称", "value": "平安银行"},
        ]))
        enriched = provider._enrich_valuation_from_tencent(profile)

        assert enriched.pe_ttm == 5.07
        assert enriched.pb == 0.47
        assert enriched.turnover_rate == 0.53
        assert enriched.market_cap == 218317000000.0
        assert "腾讯行情" in enriched.source

    def test_tencent_fallback_profile(self, monkeypatch):
        provider = AkShareProvider()
        parts = [""] * 74
        parts[1] = "报 喜 鸟"
        parts[3] = "4.69"
        parts[38] = "5.34"
        parts[39] = "16.76"
        parts[44] = "55.33"
        parts[45] = "68.44"
        parts[46] = "1.40"
        parts[72] = "1179687317"
        parts[73] = "1459333729"

        class FakeResponse:
            status_code = 200
            text = "~".join(parts)

        monkeypatch.setattr("data.providers.akshare_provider.requests.get", lambda *args, **kwargs: FakeResponse())

        profile = provider._get_stock_profile_from_tencent("002154")

        assert profile.name == "报喜鸟"
        assert profile.pe_ttm == 16.76
        assert profile.pb == 1.40
        assert profile.float_shares == 1179687317
        assert profile.total_shares == 1459333729
        assert profile.source == "腾讯行情"

    def test_health_registry_marks_unhealthy_after_threshold(self):
        registry = SourceHealthRegistry(fail_threshold=2)

        registry.mark_failure("akshare", "timeout")
        assert registry.snapshot()["akshare"]["healthy"] is True

        registry.mark_failure("akshare", "timeout")
        assert registry.snapshot()["akshare"]["healthy"] is False


class TestFundamentalDataService:

    def test_get_stock_profile_uses_provider_and_cache(self, tmp_path):
        calls = {"count": 0}

        class FakeProvider:
            def get_stock_profile(self, symbol):
                calls["count"] += 1
                return {
                    "symbol": symbol,
                    "name": "平安银行",
                    "industry": "银行Ⅱ",
                    "source": "测试源",
                }

        cache = JsonFileCache("fundamentals_test", ttl_seconds=3600, cache_dir=tmp_path)
        service = FundamentalDataService(provider=FakeProvider(), cache=cache)

        first = service.get_stock_profile("000001", "CN")
        second = service.get_stock_profile("000001", "CN")

        assert first == second
        assert first["name"] == "平安银行"
        assert calls["count"] == 1

    def test_get_stock_profile_ignores_non_cn_market(self, tmp_path):
        cache = JsonFileCache("fundamentals_test", ttl_seconds=3600, cache_dir=tmp_path)
        service = FundamentalDataService(provider=object(), cache=cache)

        assert service.get_stock_profile("AAPL", "US") is None
