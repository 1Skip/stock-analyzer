"""每日分析报告测试。"""
from reports.daily_report_service import DailyReportService
from reports.exporter import save_markdown_report


class TestDailyReportService:

    def test_render_markdown_contains_sections(self):
        service = DailyReportService(quote_service=object(), info_service=object(), recommender=object())
        content = service.render_markdown({
            "date": "2026-05-13",
            "generated_at": "2026-05-13 15:30:00",
            "market_indices": [{"symbol": "000001", "name": "上证指数", "price": 3000.12, "change_pct": 0.8}],
            "watchlist": [{
                "symbol": "000001",
                "name": "平安银行",
                "price": 11.25,
                "change_pct": -0.27,
                "signal_summary": "观望",
                "entry_hint": "等待企稳",
            }],
            "recommendations": [{
                "symbol": "600519",
                "name": "贵州茅台",
                "score": 88.5,
                "rating": "偏多",
                "latest_price": 1354.55,
            }],
            "extended_info": [{
                "symbol": "000001",
                "name": "平安银行",
                "info": {
                    "financial": {
                        "period": "20260331",
                        "metrics": {"营业总收入": 100000000, "归母净利润": 12000000},
                    },
                    "fund_flow": {
                        "date": "2026-05-13",
                        "main_net_inflow": 1000000,
                        "five_day_main_net_inflow": 5000000,
                    },
                    "news": [{"title": "测试新闻", "url": "https://example.com"}],
                },
            }],
        })

        assert "# 每日股票分析报告" in content
        assert "## 大盘温度" in content
        assert "## 自选股摘要" in content
        assert "## 今日推荐" in content
        assert "## 财务 / 资金 / 新闻摘要" in content
        assert "测试新闻" in content

    def test_save_markdown_report_writes_dated_and_latest(self, tmp_path):
        paths = save_markdown_report("# 测试", "2026-05-13", output_dir=tmp_path)

        assert (tmp_path / "2026-05-13.md").read_text(encoding="utf-8") == "# 测试"
        assert (tmp_path / "latest.md").read_text(encoding="utf-8") == "# 测试"
        assert paths["dated"].endswith("2026-05-13.md")
        assert paths["latest"].endswith("latest.md")

    def test_build_report_data_uses_injected_services(self, monkeypatch):
        class FakeQuoteService:
            def get_index_realtime(self, code):
                return {"name": "指数", "price": 3000, "change_pct": 1.2}

        class FakeInfoService:
            def get_stock_extended_info(self, symbol, market):
                return {"symbol": symbol, "financial": {}, "fund_flow": {}, "news": []}

        service = DailyReportService(
            quote_service=FakeQuoteService(),
            info_service=FakeInfoService(),
            recommender=object(),
        )
        monkeypatch.setattr(service, "_load_watchlist", lambda: [
            {"symbol": "000001", "name": "平安银行", "market": "CN"}
        ])
        monkeypatch.setattr(service, "_get_watchlist_summary", lambda items: [
            {"symbol": "000001", "name": "平安银行", "price": 11.25}
        ])
        data = service.build_report_data(report_date="2026-05-13", include_recommendations=False)

        assert data["date"] == "2026-05-13"
        assert data["market_indices"]
        assert data["watchlist"][0]["symbol"] == "000001"
        assert data["extended_info"][0]["symbol"] == "000001"
        assert data["recommendations"] == []
