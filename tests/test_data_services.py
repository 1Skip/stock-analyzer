"""分层数据服务测试。"""
import pandas as pd

from data.cache import JsonFileCache
from data.health import SourceHealthRegistry
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
        monkeypatch.setattr(akshare_provider.ak, "stock_profile_cninfo", fake_cninfo)

        profile = provider._get_stock_profile_from_tencent("000027")

        assert profile.industry == "电力、热力生产和供应业"
        assert profile.listing_date == "1993-09-03"
        assert profile.source == "腾讯行情 + 巨潮资讯"

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

    def test_info_service_uses_cache(self, tmp_path):
        calls = {"count": 0}

        class FakeProvider:
            def get_stock_extended_info(self, symbol, include_deep_layers=True):
                calls["count"] += 1
                return {"symbol": symbol, "financial": {"period": "20260331"}, "fund_flow": {}, "news": []}

        cache = JsonFileCache("stock_info_test", ttl_seconds=3600, cache_dir=tmp_path)
        service = StockInfoService(provider=FakeProvider(), cache=cache)

        first = service.get_stock_extended_info("000001", "CN")
        second = service.get_stock_extended_info("000001", "CN")

        assert first == second
        assert calls["count"] == 1

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
        assert cache.get("CN:000001:extended:v3:full") == result

    def test_extended_info_core_cache_key(self, tmp_path):
        class FakeProvider:
            def get_stock_extended_info(self, symbol, include_deep_layers=True):
                return {"symbol": symbol, "mode": "full" if include_deep_layers else "core"}

        cache = JsonFileCache("stock_info_test_v3_core", ttl_seconds=3600, cache_dir=tmp_path)
        service = StockInfoService(provider=FakeProvider(), cache=cache)

        result = service.get_stock_extended_info("000001", "CN", include_deep_layers=False)

        assert result["mode"] == "core"
        assert cache.get("CN:000001:extended:v3:core") == result

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
        }]

    def test_extended_info_provider_runs_layers_in_parallel(self, monkeypatch):
        provider = AkShareInfoProvider()
        monkeypatch.setattr(provider, "get_financial_summary", lambda symbol, timeout_seconds=4: {"period": "20260331"})
        monkeypatch.setattr(provider, "get_fund_flow_summary", lambda symbol, timeout_seconds=4: {"date": "2026-05-14"})
        monkeypatch.setattr(provider, "get_news", lambda symbol, timeout_seconds=4, limit=5: [{"title": "新闻"}])
        monkeypatch.setattr(provider, "get_research_summary", lambda symbol, timeout_seconds=4: {"reports": [{"title": "研报"}]})
        monkeypatch.setattr(provider, "get_risk_events", lambda symbol, timeout_seconds=4: {"announcements": [{"title": "公告"}]})
        monkeypatch.setattr(provider, "get_sector_attribution", lambda symbol, timeout_seconds=4: {"industry": {"name": "行业"}})

        result = provider.get_stock_extended_info("000001", timeout_seconds=1)

        assert result["financial"]["period"] == "20260331"
        assert result["fund_flow"]["date"] == "2026-05-14"
        assert result["news"][0]["title"] == "新闻"

    def test_extended_info_provider_can_skip_deep_layers(self, monkeypatch):
        provider = AkShareInfoProvider()
        monkeypatch.setattr(provider, "get_financial_summary", lambda symbol, timeout_seconds=4: {"period": "20260331"})
        monkeypatch.setattr(provider, "get_fund_flow_summary", lambda symbol, timeout_seconds=4: {"date": "2026-05-14"})
        monkeypatch.setattr(provider, "get_news", lambda symbol, timeout_seconds=4, limit=5: [{"title": "新闻"}])
        monkeypatch.setattr(provider, "get_research_summary", lambda symbol, timeout_seconds=4: {"reports": [{"title": "不应调用"}]})

        result = provider.get_stock_extended_info("000001", timeout_seconds=1, include_deep_layers=False)

        assert result["financial"]["period"] == "20260331"
        assert result["news"][0]["title"] == "新闻"
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
        release = provider._normalize_restricted_release(release_df)
        notices = provider._normalize_announcements(notice_df)

        assert lhb["times"] == 2
        assert release[0]["type"] == "首发限售"
        assert notices[0]["title"] == "关于股东减持的风险提示公告"

    def test_sector_attribution_helpers(self):
        provider = AkShareInfoProvider()
        row = pd.Series({"板块名称": "机器人概念", "涨跌幅": 2.5, "领涨股票": "测试股"})

        sector = provider._sector_row(row, "机器人概念")

        assert sector["change_pct"] == 2.5
        assert "机器人" in sector["reason"]


class TestRuntimeHelpers:

    def test_safe_call_returns_value(self):
        assert safe_call(lambda: 123, 0, label="测试") == 123

    def test_safe_call_returns_default_on_error(self):
        def fail():
            raise RuntimeError("boom")

        assert safe_call(fail, [], label="测试") == []
