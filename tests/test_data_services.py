"""分层数据服务测试。"""
import pandas as pd
import pytest

from data.cache import JsonFileCache


def test_json_file_cache_preserves_distinct_chinese_keys(tmp_path):
    cache = JsonFileCache("recommendation_t1_plans_test", ttl_seconds=3600, cache_dir=tmp_path)

    cache.set("CN:多因子稳健型:全部:5:T1", {"strategy": "多因子稳健型"})
    cache.set("CN:激进突破型:全部:5:T1", {"strategy": "激进突破型"})

    assert cache.get("CN:多因子稳健型:全部:5:T1")["strategy"] == "多因子稳健型"
    assert cache.get("CN:激进突破型:全部:5:T1")["strategy"] == "激进突破型"
    assert cache.get("CN:多因子稳健型:全部:5:T1") != cache.get("CN:激进突破型:全部:5:T1")


def test_json_file_cache_can_read_legacy_collapsed_chinese_key(tmp_path):
    cache = JsonFileCache("recommendation_t1_plans_legacy_test", ttl_seconds=3600, cache_dir=tmp_path)
    cache.path.parent.mkdir(parents=True, exist_ok=True)
    cache.path.write_text(
        '{"CN:_:_:5:T1":{"updated_at":"2099-01-01T00:00:00","value":{"strategy":"短线"}}}',
        encoding="utf-8",
    )

    assert cache.get("CN:短线:算力租赁:5:T1")["strategy"] == "短线"
from data.health import SourceHealthRegistry
from data.models import StockProfile
from data.providers.akshare_provider import AkShareProvider
from data.providers.akshare_info_provider import AkShareInfoProvider
from data.runtime import safe_call
from data.services.fundamental_service import FundamentalDataService
from data.services.info_service import StockInfoService
from data.services.quote_service import QuoteDataService


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
        assert "腾讯行情" in profile.source

    def test_tencent_fallback_enriches_cninfo_profile(self, monkeypatch):
        from data.providers import akshare_provider

        provider = AkShareProvider()
        parts = [""] * 74
        parts[1] = "深圳能源"
        parts[3] = "7.32"
        parts[38] = "1.34"
        parts[39] = "17.40"
        parts[44] = "348.24"
        parts[45] = "348.24"
        parts[46] = "1.04"
        parts[72] = "4757389916"
        parts[73] = "4757389916"

        class FakeResponse:
            status_code = 200
            text = "~".join(parts)

        def fake_cninfo(symbol):
            assert symbol == "000027"
            return pd.DataFrame([{
                "A股简称": "深圳能源",
                "所属行业": "电力、热力生产和供应业",
                "上市日期": "1993-09-03",
            }])

        monkeypatch.setattr("data.providers.akshare_provider.requests.get", lambda *args, **kwargs: FakeResponse())
        monkeypatch.setattr(provider, "_fetch_ths_company_industry", lambda symbol, timeout_seconds=2: None)
        monkeypatch.setattr(akshare_provider.ak, "stock_profile_cninfo", fake_cninfo)

        profile = provider._get_stock_profile_from_tencent("000027")

        assert profile.industry == "电力、热力生产和供应业"
        assert profile.listing_date == "1993-09-03"
        assert profile.source == "腾讯行情 + 巨潮资讯"

    def test_ths_company_industry_parser(self):
        provider = AkShareProvider()

        class FakeResponse:
            status_code = 200
            text = '<td><strong class="hltip fl">所属申万行业：</strong><span>建筑材料 — 装修建材</span></td>'
            encoding = None

            def raise_for_status(self):
                return None

        def fake_get(*args, **kwargs):
            return FakeResponse()

        from data.providers import akshare_provider
        original_get = akshare_provider.requests.get
        akshare_provider.requests.get = fake_get
        try:
            assert provider._fetch_ths_company_industry("002066") == "建筑材料 — 装修建材"
        finally:
            akshare_provider.requests.get = original_get

    def test_ths_company_industry_takes_priority(self, monkeypatch):
        provider = AkShareProvider()
        base = StockProfile(symbol="002066", name="瑞泰科技", industry="C 制造业", source="AKShare/东方财富")

        monkeypatch.setattr(provider, "_fetch_ths_company_industry", lambda symbol, timeout_seconds=2: "建筑材料 — 装修建材")

        profile = provider._enrich_industry_from_ths_company(base)

        assert profile.industry == "建筑材料 — 装修建材"
        assert "同花顺公司概况" in profile.source

    def test_cninfo_enrichment_replaces_coarse_industry(self, monkeypatch):
        from data.providers import akshare_provider

        provider = AkShareProvider()
        base = StockProfile(
            symbol="002066",
            name="瑞泰科技",
            industry="C 制造业",
            listing_date="2006-08-23",
            source="深交所A股",
        )

        def fake_cninfo(symbol):
            assert symbol == "002066"
            return pd.DataFrame([{
                "A股简称": "瑞泰科技",
                "所属行业": "非金属矿物制品业",
                "上市日期": "2006-08-23",
            }])

        monkeypatch.setattr(akshare_provider.ak, "stock_profile_cninfo", fake_cninfo)

        profile = provider._enrich_profile_from_cninfo(base)

        assert profile.industry == "非金属矿物制品业"
        assert profile.listing_date == "2006-08-23"

    def test_cninfo_does_not_override_ths_industry(self, monkeypatch):
        from data.providers import akshare_provider

        provider = AkShareProvider()
        base = StockProfile(
            symbol="688981",
            name="中芯国际",
            industry="电子 — 半导体",
            listing_date="2020-07-16",
            source="腾讯行情 + 同花顺公司概况",
        )

        def fake_cninfo(symbol):
            assert symbol == "688981"
            return pd.DataFrame([{
                "A股简称": "中芯国际",
                "所属行业": "计算机、通信和其他电子设备制造业",
                "上市日期": "2020-07-16",
            }])

        monkeypatch.setattr(akshare_provider.ak, "stock_profile_cninfo", fake_cninfo)

        profile = provider._enrich_profile_from_cninfo(base)

        assert profile.industry == "电子 — 半导体"
        assert profile.listing_date == "2020-07-16"

    def test_profile_index_merges_exchange_rows(self):
        provider = AkShareProvider()
        index = {}

        provider._merge_szse_profile_rows(index, pd.DataFrame([{
            "A股代码": "000001",
            "A股简称": "平安银行",
            "A股上市日期": "1991-04-03",
            "A股总股本": "19,405,918,198",
            "A股流通股本": "19,405,685,028",
            "所属行业": "J 金融业",
        }]), "深交所A股")
        provider._merge_bse_profile_rows(index, pd.DataFrame([{
            "证券代码": "831396",
            "证券简称": "许昌智能",
            "上市日期": "2024-01-26",
            "所属行业": "电气机械和器材制造业",
        }]), "北交所")

        assert index["000001"]["industry"] == "J 金融业"
        assert index["000001"]["listing_date"] == "1991-04-03"
        assert index["831396"]["industry"] == "电气机械和器材制造业"
        assert index["831396"]["listing_date"] == "2024-01-26"

    def test_profile_enrichment_matches_renumbered_bse_stock_by_name(self, monkeypatch):
        provider = AkShareProvider()

        monkeypatch.setattr(provider, "get_stock_profile_index", lambda timeout_seconds=5: {
            "920496": {
                "symbol": "920496",
                "name": "许昌智能",
                "industry": "电气机械和器材制造业",
                "listing_date": "2024-01-26",
                "source": "北交所",
            }
        })

        profile = provider._enrich_profile_from_full_index(
            StockProfile(symbol="831396", name="许昌智能(已切换)", industry="-", source="腾讯行情"),
            symbol="831396",
        )

        assert profile.name == "许昌智能"
        assert profile.industry == "电气机械和器材制造业"
        assert profile.listing_date == "2024-01-26"
        assert "现代码920496" in profile.source

    def test_profile_enrichment_returns_index_profile_when_realtime_missing(self, monkeypatch):
        provider = AkShareProvider()

        monkeypatch.setattr(provider, "get_stock_profile_index", lambda timeout_seconds=5: {
            "000001": {
                "symbol": "000001",
                "name": "平安银行",
                "industry": "J 金融业",
                "listing_date": "1991-04-03",
                "source": "深交所A股",
            }
        })

        profile = provider._enrich_profile_from_full_index(None, symbol="000001")

        assert profile.symbol == "000001"
        assert profile.industry == "J 金融业"
        assert profile.listing_date == "1991-04-03"

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

    def test_get_stock_profile_fills_missing_fields_from_full_index(self, tmp_path):
        class FakeProvider:
            def get_stock_profile(self, symbol):
                return {
                    "symbol": symbol,
                    "name": "许昌智能",
                    "source": "腾讯行情",
                }

            def get_stock_profile_index(self):
                return {
                    "831396": {
                        "symbol": "831396",
                        "industry": "电气机械和器材制造业",
                        "listing_date": "2024-01-26",
                        "source": "北交所",
                    }
                }

        cache = JsonFileCache("fundamentals_test_fill", ttl_seconds=3600, cache_dir=tmp_path)
        service = FundamentalDataService(provider=FakeProvider(), cache=cache)
        service.index_cache = JsonFileCache("fundamentals_index_test_fill", ttl_seconds=3600, cache_dir=tmp_path)

        result = service.get_stock_profile("831396", "CN")

        assert result["industry"] == "电气机械和器材制造业"
        assert result["listing_date"] == "2024-01-26"
        assert "北交所" in result["source"]

    def test_cached_profile_fills_missing_fields_from_full_index(self, tmp_path):
        class FakeProvider:
            def get_stock_profile(self, symbol):
                raise AssertionError("缓存缺字段时应先用全量索引补齐")

            def get_stock_profile_index(self):
                return {
                    "000001": {
                        "symbol": "000001",
                        "industry": "J 金融业",
                        "listing_date": "1991-04-03",
                        "source": "深交所A股",
                    }
                }

        cache = JsonFileCache("fundamentals_test_cached_fill", ttl_seconds=3600, cache_dir=tmp_path)
        cache.set("CN:000001:profile", {"symbol": "000001", "name": "平安银行", "source": "腾讯行情"})
        service = FundamentalDataService(provider=FakeProvider(), cache=cache)
        service.index_cache = JsonFileCache("fundamentals_index_test_cached_fill", ttl_seconds=3600, cache_dir=tmp_path)

        result = service.get_stock_profile("000001", "CN")

        assert result["industry"] == "J 金融业"
        assert result["listing_date"] == "1991-04-03"

    def test_cached_profile_matches_renumbered_bse_stock_by_name(self, tmp_path):
        class FakeProvider:
            def get_stock_profile(self, symbol):
                raise AssertionError("缓存应通过全量索引按名称补齐")

            def get_stock_profile_index(self):
                return {
                    "920496": {
                        "symbol": "920496",
                        "name": "许昌智能",
                        "industry": "电气机械和器材制造业",
                        "listing_date": "2024-01-26",
                        "source": "北交所",
                    }
                }

        cache = JsonFileCache("fundamentals_test_renumbered_fill", ttl_seconds=3600, cache_dir=tmp_path)
        cache.set("CN:831396:profile", {"symbol": "831396", "name": "许昌智能(已切换)", "industry": "-", "source": "腾讯行情"})
        service = FundamentalDataService(provider=FakeProvider(), cache=cache)
        service.index_cache = JsonFileCache("fundamentals_index_test_renumbered_fill", ttl_seconds=3600, cache_dir=tmp_path)

        result = service.get_stock_profile("831396", "CN")

        assert result["name"] == "许昌智能"
        assert result["industry"] == "电气机械和器材制造业"
        assert result["listing_date"] == "2024-01-26"
        assert "现代码920496" in result["source"]

    def test_cached_coarse_industry_triggers_provider_refresh(self, tmp_path):
        class FakeProvider:
            def get_stock_profile(self, symbol):
                return {
                    "symbol": symbol,
                    "name": "瑞泰科技",
                    "industry": "非金属矿物制品业",
                    "listing_date": "2006-08-23",
                    "source": "腾讯行情 + 巨潮资讯",
                }

            def get_stock_profile_index(self):
                return {
                    "002066": {
                        "symbol": "002066",
                        "name": "瑞泰科技",
                        "industry": "C 制造业",
                        "listing_date": "2006-08-23",
                        "source": "深交所A股",
                    }
                }

        cache = JsonFileCache("fundamentals_test_coarse_refresh", ttl_seconds=3600, cache_dir=tmp_path)
        cache.set(
            "CN:002066:profile",
            {
                "symbol": "002066",
                "name": "瑞泰科技",
                "industry": "C 制造业",
                "listing_date": "2006-08-23",
                "source": "深交所A股",
            },
        )
        service = FundamentalDataService(provider=FakeProvider(), cache=cache)
        service.index_cache = JsonFileCache("fundamentals_index_test_coarse_refresh", ttl_seconds=3600, cache_dir=tmp_path)

        result = service.get_stock_profile("002066", "CN")

        assert result["industry"] == "非金属矿物制品业"
        assert result["listing_date"] == "2006-08-23"

    def test_cached_non_ths_industry_triggers_provider_refresh(self, tmp_path):
        class FakeProvider:
            def _enrich_industry_from_ths_company(self, profile, timeout_seconds=2):
                return profile

            def get_stock_profile(self, symbol):
                return {
                    "symbol": symbol,
                    "name": "瑞泰科技",
                    "industry": "建筑材料 — 装修建材",
                    "listing_date": "2006-08-23",
                    "source": "AKShare/东方财富 + 同花顺公司概况 + 腾讯行情",
                }

            def get_stock_profile_index(self):
                return {}

        cache = JsonFileCache("fundamentals_test_ths_refresh", ttl_seconds=3600, cache_dir=tmp_path)
        cache.set(
            "CN:002066:profile",
            {
                "symbol": "002066",
                "name": "瑞泰科技",
                "industry": "装修建材",
                "listing_date": "2006-08-23",
                "source": "AKShare/东方财富 + 腾讯行情",
            },
        )
        service = FundamentalDataService(provider=FakeProvider(), cache=cache)
        service.index_cache = JsonFileCache("fundamentals_index_test_ths_refresh", ttl_seconds=3600, cache_dir=tmp_path)

        result = service.get_stock_profile("002066", "CN")

        assert result["industry"] == "建筑材料 — 装修建材"
        assert "同花顺公司概况" in result["source"]

    def test_missing_provider_profile_can_return_index_profile(self, tmp_path):
        class FakeProvider:
            def get_stock_profile(self, symbol):
                return None

            def get_stock_profile_index(self):
                return {
                    "000001": {
                        "symbol": "000001",
                        "name": "平安银行",
                        "industry": "J 金融业",
                        "listing_date": "1991-04-03",
                        "source": "深交所A股",
                    }
                }

        cache = JsonFileCache("fundamentals_test_index_only", ttl_seconds=3600, cache_dir=tmp_path)
        service = FundamentalDataService(provider=FakeProvider(), cache=cache)
        service.index_cache = JsonFileCache("fundamentals_index_test_index_only", ttl_seconds=3600, cache_dir=tmp_path)

        result = service.get_stock_profile("000001", "CN")

        assert result["name"] == "平安银行"
        assert result["industry"] == "J 金融业"
        assert result["listing_date"] == "1991-04-03"


class TestQuoteDataService:

    def test_quote_service_delegates_to_provider(self):
        calls = []

        class FakeProvider:
            def get_stock_data(self, symbol, period, market):
                calls.append(("data", symbol, period, market))
                return "df"

            def get_realtime_quote(self, symbol, market):
                calls.append(("quote", symbol, market))
                return {"price": 12.3}

            def get_intraday_data(self, symbol, market):
                calls.append(("intraday", symbol, market))
                return "intraday"

            def get_index_realtime(self, symbol):
                calls.append(("index", symbol))
                return {"price": 3000}

            def get_preferred_source(self):
                calls.append(("get_source",))
                return "auto"

            def set_preferred_source(self, source):
                calls.append(("set_source", source))
                return True

        service = QuoteDataService(provider=FakeProvider())

        assert service.get_stock_data("000001.0", "1y", "CN") == "df"
        assert service.get_realtime_quote("aapl", "US") == {"price": 12.3}
        assert service.get_intraday_data("000001", "CN") == "intraday"
        assert service.get_index_realtime("000001.0") == {"price": 3000}
        assert service.get_preferred_source() == "auto"
        assert service.set_preferred_source("sina") is True
        assert calls == [
            ("data", "000001", "1y", "CN"),
            ("quote", "AAPL", "US"),
            ("intraday", "000001", "CN"),
            ("index", "000001"),
            ("get_source",),
            ("set_source", "sina"),
        ]

    def test_quote_service_skips_intraday_for_non_cn(self):
        class FakeProvider:
            def get_intraday_data(self, symbol, market):
                raise AssertionError("非 A 股不应请求分时 provider")

        service = QuoteDataService(provider=FakeProvider())

        assert service.get_intraday_data("AAPL", "US") is None

    def test_quote_service_batch_filters_empty_symbols(self):
        class FakeProvider:
            def get_batch_realtime_quotes(self, symbols, market):
                return {symbol: {"price": index} for index, symbol in enumerate(symbols)}

        service = QuoteDataService(provider=FakeProvider())

        quotes = service.get_batch_realtime_quotes(["000001", "", None, "600519.0"], "CN")

        assert list(quotes) == ["000001", "600519"]

    def test_quote_service_fetch_multiple_stocks_normalizes_codes(self):
        class FakeProvider:
            def fetch_multiple_stocks(self, stocks, period, market, max_workers):
                return {
                    "stocks": stocks,
                    "period": period,
                    "market": market,
                    "max_workers": max_workers,
                }

        service = QuoteDataService(provider=FakeProvider())

        result = service.fetch_multiple_stocks(
            [{"code": "000001.0", "name": "平安银行"}, {"code": "", "name": "空"}],
            period="6mo",
            market="CN",
            max_workers=3,
        )

        assert result["stocks"] == [{"code": "000001", "name": "平安银行"}]
        assert result["period"] == "6mo"
        assert result["max_workers"] == 3


class TestStockInfoService:

    def test_normalize_financial_summary(self):
        provider = AkShareInfoProvider()
        df = pd.DataFrame([
            {"指标": "营业总收入", "20260331": 100000000.0, "20251231": 90000000.0},
            {"指标": "归母净利润", "20260331": 12000000.0, "20251231": 11000000.0},
            {"指标": "经营现金流量净额", "20260331": -3000000.0, "20251231": 5000000.0},
        ])

        result = provider._normalize_financial_summary(df)

        assert result["period"] == "20260331"
        assert result["metrics"]["营业总收入"] == 100000000.0
        assert result["metrics"]["归母净利润"] == 12000000.0
        assert result["metrics"]["经营现金流量净额"] == -3000000.0

        assert result["history"][-1]["period"] == "20260331"
        assert any(value == 12000000.0 for key, value in result["history"][-1].items() if key != "period")

    def test_financial_indicator_em_keeps_profit_history_for_peg(self):
        provider = AkShareInfoProvider()
        df = pd.DataFrame([
            {"REPORT_DATE": "2024-12-31", "PARENT_NETPROFIT": 100.0, "EPSJB": 0.5},
            {"REPORT_DATE": "2025-12-31", "PARENT_NETPROFIT": 121.0, "EPSJB": 0.6},
            {"REPORT_DATE": "2026-12-31", "PARENT_NETPROFIT": 144.0, "EPSJB": 0.7},
        ])

        result = provider._normalize_financial_indicator_em(df)

        assert len(result["history"]) == 3
        assert any(value == 144.0 for key, value in result["history"][-1].items() if key != "period")

    def test_financial_summary_falls_back_to_secondary_source(self, monkeypatch):
        provider = AkShareInfoProvider()
        calls = []

        def fake_run(func, timeout_seconds):
            calls.append(len(calls))
            if len(calls) == 1:
                raise RuntimeError("primary down")
            return pd.DataFrame([{"指标": "每股收益", "20260331": 0.32}])

        monkeypatch.setattr("data.providers.akshare_info_provider.run_with_timeout", fake_run)

        result = provider.get_financial_summary("002609")

        assert result["source"] == "同花顺财务摘要"
        assert result["metrics"]["每股收益"] == 0.32

    def test_normalize_fund_flow_summary(self):
        provider = AkShareInfoProvider()
        df = pd.DataFrame([
            {"日期": "2026-05-08", "主力净流入-净额": 100.0, "主力净流入-净占比": 1.5, "超大单净流入-净额": 30.0, "大单净流入-净额": 70.0},
            {"日期": "2026-05-11", "主力净流入-净额": -20.0, "主力净流入-净占比": -0.5, "超大单净流入-净额": -10.0, "大单净流入-净额": -10.0},
        ])

        result = provider._normalize_fund_flow_summary(df)

        assert result["date"] == "2026-05-11"
        assert result["main_net_inflow"] == -20.0
        assert result["main_net_inflow_ratio"] == -0.5
        assert result["five_day_main_net_inflow"] == 80.0

    def test_fund_flow_falls_back_to_main_fund_flow(self, monkeypatch):
        provider = AkShareInfoProvider()
        calls = []

        def fake_run(func, timeout_seconds):
            calls.append(len(calls))
            if len(calls) == 1:
                return pd.DataFrame()
            return pd.DataFrame([{"代码": "002609", "主力净流入": 1234.0, "主力净占比": 2.5}])

        monkeypatch.setattr("data.providers.akshare_info_provider.run_with_timeout", fake_run)

        result = provider.get_fund_flow_summary("002609")

        assert result["source"] == "东方财富主力资金流"
        assert result["main_net_inflow"] == 1234.0
        assert result["main_net_inflow_ratio"] == 2.5

    def test_info_service_uses_cache(self, tmp_path):
        calls = {"count": 0}

        class FakeProvider:
            def get_stock_extended_info(self, symbol, include_deep_layers=True):
                calls["count"] += 1
                return {
                    "symbol": symbol,
                    "financial": {"period": "20260331"},
                    "fund_flow": {"main_net_inflow": 30_000_000},
                    "news": [],
                }

        cache = JsonFileCache("stock_info_test", ttl_seconds=3600, cache_dir=tmp_path)
        service = StockInfoService(provider=FakeProvider(), cache=cache)

        first = service.get_stock_extended_info("000001", "CN")
        second = service.get_stock_extended_info("000001", "CN")

        assert first == second
        assert calls["count"] == 1

    def test_info_service_reuses_split_layer_caches(self, tmp_path):
        calls = {"count": 0}

        class FakeProvider:
            def get_stock_extended_info(self, symbol, include_deep_layers=True):
                calls["count"] += 1
                return {
                    "symbol": symbol,
                    "financial": {"metrics": {"归母净利润": 1}},
                    "fund_flow": {"main_net_inflow": 30_000_000},
                    "news": [],
                    "market_news": [],
                    "research": {"reports": []},
                    "dividend": {},
                    "risk_events": {"announcements": []},
                    "sector_attribution": {"industry": {}, "concepts": []},
                }

        cache = JsonFileCache("stock_info_split_bundle", ttl_seconds=0, cache_dir=tmp_path)
        service = StockInfoService(provider=FakeProvider(), cache=cache)
        service.financial_cache = JsonFileCache("stock_financial_split", ttl_seconds=3600, cache_dir=tmp_path)
        service.fund_flow_cache = JsonFileCache("stock_fund_flow_split", ttl_seconds=3600, cache_dir=tmp_path)
        service.research_cache = JsonFileCache("stock_research_split", ttl_seconds=3600, cache_dir=tmp_path)
        service.risk_cache = JsonFileCache("stock_risk_split", ttl_seconds=3600, cache_dir=tmp_path)

        first = service.get_stock_extended_info("000001", "CN")
        second = service.get_stock_extended_info("000001", "CN")

        assert first["financial"] == second["financial"]
        assert second["fund_flow"]["main_net_inflow"] == 30_000_000
        assert second["risk_events"]["announcements"] == []
        assert calls["count"] == 1

    def test_info_service_ignores_empty_fund_flow_split_cache(self, tmp_path):
        calls = {"count": 0}

        class FakeProvider:
            def get_stock_extended_info(self, symbol, include_deep_layers=True):
                calls["count"] += 1
                return {
                    "symbol": symbol,
                    "financial": {"metrics": {"归母净利润": 1}},
                    "fund_flow": {"main_net_inflow": 30_000_000},
                    "news": [],
                    "market_news": [],
                    "research": {"reports": []},
                    "dividend": {},
                    "risk_events": {"announcements": []},
                    "sector_attribution": {"industry": {}, "concepts": []},
                }

        cache = JsonFileCache("stock_info_empty_fund_bundle", ttl_seconds=0, cache_dir=tmp_path)
        service = StockInfoService(provider=FakeProvider(), cache=cache)
        service.financial_cache = JsonFileCache("stock_financial_empty_fund", ttl_seconds=3600, cache_dir=tmp_path)
        service.fund_flow_cache = JsonFileCache("stock_fund_flow_empty_fund", ttl_seconds=3600, cache_dir=tmp_path)
        service.research_cache = JsonFileCache("stock_research_empty_fund", ttl_seconds=3600, cache_dir=tmp_path)
        service.risk_cache = JsonFileCache("stock_risk_empty_fund", ttl_seconds=3600, cache_dir=tmp_path)

        service.financial_cache.set("CN:000001:financial:v1", {"metrics": {"归母净利润": 1}})
        service.fund_flow_cache.set("CN:000001:fund_flow:v1", {})

        result = service.get_stock_extended_info("000001", "CN")

        assert result["fund_flow"]["main_net_inflow"] == 30_000_000
        assert calls["count"] == 1

    def test_info_service_does_not_cache_empty_fund_flow_layer(self, tmp_path):
        class FakeProvider:
            def get_stock_extended_info(self, symbol, include_deep_layers=True):
                return {
                    "symbol": symbol,
                    "financial": {"metrics": {"归母净利润": 1}},
                    "fund_flow": {},
                    "news": [],
                    "market_news": [],
                    "research": {"reports": []},
                    "dividend": {},
                    "risk_events": {"announcements": []},
                    "sector_attribution": {"industry": {}, "concepts": []},
                }

        cache = JsonFileCache("stock_info_empty_layer_bundle", ttl_seconds=3600, cache_dir=tmp_path)
        service = StockInfoService(provider=FakeProvider(), cache=cache)
        service.financial_cache = JsonFileCache("stock_financial_empty_layer", ttl_seconds=3600, cache_dir=tmp_path)
        service.fund_flow_cache = JsonFileCache("stock_fund_flow_empty_layer", ttl_seconds=3600, cache_dir=tmp_path)

        result = service.get_stock_extended_info("000001", "CN")

        assert result["fund_flow"] == {}
        assert service.financial_cache.get("CN:000001:financial:v1")["metrics"]["归母净利润"] == 1
        assert service.fund_flow_cache.get("CN:000001:fund_flow:v1") is None
        assert cache.get("CN:000001:extended:v5:full") is None

    def test_extended_info_uses_v3_cache_key(self, tmp_path):
        class FakeProvider:
            def get_stock_extended_info(self, symbol, include_deep_layers=True):
                return {"symbol": symbol, "research": {"reports": []}}

        cache = JsonFileCache("stock_info_test_v2", ttl_seconds=3600, cache_dir=tmp_path)
        service = StockInfoService(provider=FakeProvider(), cache=cache)

        result = service.get_stock_extended_info("000001", "CN")

        assert result["research"]["reports"] == []
        assert cache.get("CN:000001:extended") is None
        assert cache.get("CN:000001:extended:v2") is None
        assert cache.get("CN:000001:extended:v3:full") is None
        assert cache.get("CN:000001:extended:v4:full") is None
        assert cache.get("CN:000001:extended:v5:full") is None

    def test_extended_info_core_cache_key(self, tmp_path):
        class FakeProvider:
            def get_stock_extended_info(self, symbol, include_deep_layers=True):
                return {
                    "symbol": symbol,
                    "mode": "full" if include_deep_layers else "core",
                    "financial": {"metrics": {"归母净利润": 1}},
                    "fund_flow": {"main_net_inflow": 30_000_000},
                }

        cache = JsonFileCache("stock_info_test_v3_core", ttl_seconds=3600, cache_dir=tmp_path)
        service = StockInfoService(provider=FakeProvider(), cache=cache)

        result = service.get_stock_extended_info("000001", "CN", include_deep_layers=False)

        assert result["mode"] == "core"
        assert cache.get("CN:000001:extended:v4:core") is None
        assert cache.get("CN:000001:extended:v5:core") == result

    def test_info_service_ignores_non_cn_market(self, tmp_path):
        cache = JsonFileCache("stock_info_test", ttl_seconds=3600, cache_dir=tmp_path)
        service = StockInfoService(provider=object(), cache=cache)

        assert service.get_stock_extended_info("AAPL", "US") is None

    def test_normalize_research_reports(self):
        provider = AkShareInfoProvider()
        df = pd.DataFrame([{
            "报告名称": "银行业深度报告",
            "报告日期": "2026-05-13",
            "机构名称": "测试证券",
            "评级": "买入",
            "PDF链接": "https://example.com/report.pdf",
        }])

        result = provider._normalize_research_reports(df)

        assert result[0]["title"] == "银行业深度报告"
        assert result[0]["pdf_url"] == "https://example.com/report.pdf"

    def test_research_reports_fall_back_to_profit_forecast(self, monkeypatch):
        provider = AkShareInfoProvider()
        calls = []

        def fake_run(func, timeout_seconds):
            calls.append(len(calls))
            if len(calls) == 1:
                raise RuntimeError("report down")
            return pd.DataFrame([{"机构名称": "测试证券", "评级": "买入", "报告日期": "2026-05-14"}])

        monkeypatch.setattr("data.providers.akshare_info_provider.run_with_timeout", fake_run)

        result = provider.get_research_reports("002609")

        assert result[0]["source"] == "东方财富盈利预测"
        assert result[0]["rating"] == "买入"

    def test_normalize_dividend_summary_prefers_implemented_plan(self):
        provider = AkShareInfoProvider()
        df = pd.DataFrame([
            {"公告日期": "2026-04-30", "派息": 0.85, "进度": "预案", "除权除息日": None},
            {"公告日期": "2025-05-23", "派息": 0.70, "进度": "实施", "除权除息日": "2025-05-30"},
        ])

        result = provider._normalize_dividend_summary(df)

        assert result["source"] == "新浪财经历史分红"
        assert result["cash_dividend_per_10"] == 0.70
        assert result["cash_dividend_per_share"] == pytest.approx(0.07)
        assert result["progress"] == "实施"

    def test_normalize_cninfo_dividend_summary_uses_cash_ratio(self):
        provider = AkShareInfoProvider()
        df = pd.DataFrame([{
            "实施方案公告日期": "2026-05-08",
            "派息比例": 1.50,
            "除权除息日": "2026-05-16",
            "实施方案分红说明": "10派1.5元",
        }])

        result = provider._normalize_cninfo_dividend_summary(df)

        assert result["status"] == "ok"
        assert result["source"] == "巨潮资讯历史分红"
        assert result["cash_dividend_per_10"] == 1.50
        assert result["cash_dividend_per_share"] == pytest.approx(0.15)

    def test_normalize_sina_dividend_overview_as_last_resort(self):
        provider = AkShareInfoProvider()
        df = pd.DataFrame([{
            "代码": "002609",
            "名称": "捷顺科技",
            "年均股息": 0.50,
            "分红次数": 8,
        }])

        result = provider._normalize_sina_dividend_overview("002609", df)

        assert result["status"] == "ok"
        assert result["source"] == "新浪财经历史分红摘要"
        assert result["annual_dividend_per_share"] == pytest.approx(0.05)
        assert "非最近一期" in result["note"]

    def test_normalize_eps_consensus_empty_has_status_from_public_method(self, monkeypatch):
        provider = AkShareInfoProvider()

        calls = []

        def fake_run(func, timeout_seconds):
            calls.append(len(calls))
            return pd.DataFrame([{"预测机构数": 3}])

        monkeypatch.setattr("data.providers.akshare_info_provider.run_with_timeout", fake_run)

        result = provider.get_eps_consensus("002609")

        assert result["status"] == "source_empty"
        assert result["source"] == "同花顺/东方财富盈利预测"
        assert "同花顺盈利预测返回空数据" in result["reason"]
        assert "东方财富盈利预测返回空数据" in result["reason"]

    def test_eps_consensus_falls_back_to_eastmoney(self, monkeypatch):
        provider = AkShareInfoProvider()
        calls = []

        def fake_run(func, timeout_seconds):
            calls.append(len(calls))
            if len(calls) == 1:
                return pd.DataFrame([{"预测机构数": 3}])
            return pd.DataFrame([{"2026预测每股收益": 0.88}])

        monkeypatch.setattr("data.providers.akshare_info_provider.run_with_timeout", fake_run)

        result = provider.get_eps_consensus("002609")

        assert result["source"] == "东方财富盈利预测"
        assert result["values"]["2026预测每股收益"] == 0.88

    def test_normalize_news_accepts_eastmoney_columns(self):
        provider = AkShareInfoProvider()
        df = pd.DataFrame([{
            "新闻标题": "测试新闻",
            "发布时间": "2026-05-14 10:00:00",
            "新闻链接": "https://example.com/news",
        }])

        result = provider._normalize_news(df)

        assert result == [{
            "title": "测试新闻",
            "date": "2026-05-14 10:00:00",
            "url": "https://example.com/news",
            "source": "",
        }]

    def test_normalize_market_news_accepts_caixin_columns(self):
        provider = AkShareInfoProvider()
        df = pd.DataFrame([{
            "tag": "市场动态",
            "summary": "海外流动性扰动影响风险偏好",
            "url": "https://example.com/market",
        }])

        result = provider._normalize_market_news(df)

        assert result == [{
            "title": "海外流动性扰动影响风险偏好",
            "summary": "海外流动性扰动影响风险偏好",
            "tag": "市场动态",
            "date": "",
            "url": "https://example.com/market",
            "source": "财新数据通",
        }]

    def test_market_news_merges_caixin_and_cls_sources(self, monkeypatch):
        provider = AkShareInfoProvider()
        calls = []

        def fake_run(func, timeout_seconds):
            calls.append(len(calls))
            if len(calls) == 1:
                return pd.DataFrame([{"summary": "财新市场快讯", "url": "https://example.com/a"}])
            return pd.DataFrame([{"标题": "财联社快讯", "链接": "https://example.com/b"}])

        monkeypatch.setattr("data.providers.akshare_info_provider.run_with_timeout", fake_run)

        result = provider.get_market_news(limit=5)

        assert [item["source"] for item in result] == ["财新数据通", "财联社资讯"]
        assert result[0]["title"] == "财新市场快讯"

    def test_stock_news_falls_back_to_cls_filtered_news(self, monkeypatch):
        provider = AkShareInfoProvider()
        calls = []

        def fake_run(func, timeout_seconds):
            calls.append(len(calls))
            if len(calls) == 1:
                return pd.DataFrame()
            return pd.DataFrame([{"标题": "002609 公司公告相关快讯", "链接": "https://example.com/c"}])

        monkeypatch.setattr("data.providers.akshare_info_provider.run_with_timeout", fake_run)

        result = provider.get_news("002609")

        assert result[0]["source"] == "财联社资讯"
        assert "002609" in result[0]["title"]

    def test_extended_info_provider_runs_layers_in_parallel(self, monkeypatch):
        provider = AkShareInfoProvider()
        monkeypatch.setattr(provider, "get_financial_summary", lambda symbol, timeout_seconds=4: {"period": "20260331"})
        monkeypatch.setattr(provider, "get_fund_flow_summary", lambda symbol, timeout_seconds=4: {"date": "2026-05-14"})
        monkeypatch.setattr(provider, "get_news", lambda symbol, timeout_seconds=4, limit=5: [{"title": "新闻"}])
        monkeypatch.setattr(provider, "get_market_news", lambda timeout_seconds=4, limit=8: [{"title": "市场快讯"}])
        monkeypatch.setattr(provider, "get_research_summary", lambda symbol, timeout_seconds=4: {"reports": [{"title": "研报"}]})
        monkeypatch.setattr(provider, "get_risk_events", lambda symbol, timeout_seconds=4: {"announcements": [{"title": "公告"}]})
        monkeypatch.setattr(provider, "get_sector_attribution", lambda symbol, timeout_seconds=4: {"industry": {"name": "行业"}})

        result = provider.get_stock_extended_info("000001", timeout_seconds=1)

        assert result["financial"]["period"] == "20260331"
        assert result["fund_flow"]["date"] == "2026-05-14"
        assert result["news"][0]["title"] == "新闻"
        assert result["market_news"][0]["title"] == "市场快讯"

    def test_extended_info_provider_can_skip_deep_layers(self, monkeypatch):
        provider = AkShareInfoProvider()
        monkeypatch.setattr(provider, "get_financial_summary", lambda symbol, timeout_seconds=4: {"period": "20260331"})
        monkeypatch.setattr(provider, "get_fund_flow_summary", lambda symbol, timeout_seconds=4: {"date": "2026-05-14"})
        monkeypatch.setattr(provider, "get_news", lambda symbol, timeout_seconds=4, limit=5: [{"title": "新闻"}])
        monkeypatch.setattr(provider, "get_market_news", lambda timeout_seconds=4, limit=8: [{"title": "市场快讯"}])
        monkeypatch.setattr(provider, "get_research_summary", lambda symbol, timeout_seconds=4: {"reports": [{"title": "不应调用"}]})

        result = provider.get_stock_extended_info("000001", timeout_seconds=1, include_deep_layers=False)

        assert result["financial"]["period"] == "20260331"
        assert result["news"][0]["title"] == "新闻"
        assert result["market_news"][0]["title"] == "市场快讯"
        assert result["research"]["reports"] == []

    def test_normalize_risk_events(self):
        provider = AkShareInfoProvider()
        lhb_df = pd.DataFrame([{
            "代码": "000001",
            "上榜次数": 2,
            "净买额": 12000000,
            "上榜原因": "日涨幅偏离值达7%",
        }])
        release_df = pd.DataFrame([{
            "解禁日期": "2026-06-01",
            "解禁数量": 1000000,
            "实际解禁市值": 50000000,
            "占总股本比例": 1.2,
            "解禁类型": "首发限售",
        }])
        notice_df = pd.DataFrame([{
            "公告标题": "关于股东减持的风险提示公告",
            "公告日期": "2026-05-13",
            "公告类型": "风险提示",
            "公告链接": "https://example.com/notice",
        }])

        lhb = provider._normalize_lhb_summary("000001", lhb_df)
        release = provider._normalize_restricted_release(release_df, source="测试限售")
        notices = provider._normalize_announcements(notice_df, source="测试公告")

        assert lhb["times"] == 2
        assert release[0]["type"] == "首发限售"
        assert release[0]["source"] == "测试限售"
        assert notices[0]["title"] == "关于股东减持的风险提示公告"
        assert notices[0]["source"] == "测试公告"

    def test_announcements_fall_back_to_market_notice(self, monkeypatch):
        provider = AkShareInfoProvider()
        calls = []

        def fake_run(func, timeout_seconds):
            calls.append(len(calls))
            if len(calls) == 1:
                return pd.DataFrame()
            return pd.DataFrame([{"代码": "002609", "公告标题": "风险提示公告", "公告日期": "2026-05-14"}])

        monkeypatch.setattr("data.providers.akshare_info_provider.run_with_timeout", fake_run)

        result = provider.get_announcements("002609")

        assert result[0]["title"] == "风险提示公告"
        assert result[0]["source"] == "东方财富全市场公告"

    def test_sector_attribution_helpers(self):
        provider = AkShareInfoProvider()
        row = pd.Series({"板块名称": "机器人概念", "涨跌幅": 2.5, "领涨股票": "测试股"})

        sector = provider._sector_row(row, "机器人概念", source="测试板块")

        assert sector["change_pct"] == 2.5
        assert "机器人" in sector["reason"]
        assert sector["source"] == "测试板块"


class TestRuntimeHelpers:

    def test_safe_call_returns_value(self):
        assert safe_call(lambda: 123, 0, label="测试") == 123

    def test_safe_call_returns_default_on_error(self):
        def fail():
            raise RuntimeError("boom")

        assert safe_call(fail, [], label="测试") == []
