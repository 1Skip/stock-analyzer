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
                    "market_news": [{"tag": "市场动态", "title": "测试市场快讯", "url": "https://example.com/market"}],
                    "research": {
                        "eps_consensus": {"values": {"2026预测EPS": 1.23}},
                        "reports": [{
                            "title": "测试研报",
                            "date": "2026-05-13",
                            "org": "测试证券",
                            "rating": "买入",
                            "pdf_url": "https://example.com/report.pdf",
                        }],
                    },
                    "risk_events": {
                        "lhb": {"period": "近一月", "times": 2, "net_amount": 10000000},
                        "restricted_release": [{
                            "date": "2026-06-01",
                            "shares": 1000000,
                            "market_value": 50000000,
                        }],
                        "announcements": [{
                            "title": "股东减持风险提示公告",
                            "type": "风险提示",
                        }],
                    },
                    "sector_attribution": {
                        "industry": {"name": "银行", "change_pct": 1.2, "reason": "息差改善"},
                        "concepts": [{"name": "机器人概念", "change_pct": 2.5}],
                    },
                },
            }],
        })

        assert "# 每日股票决策仪表盘" in content
        assert "## 核心结论" in content
        assert "## 大盘温度" in content
        assert "## 自选股决策仪表盘" in content
        assert "## 推荐池" in content
        assert "## 研报 / 风险 / 板块归因" in content
        assert "## 操作检查清单" in content
        assert "测试新闻" in content
        assert "测试市场快讯" in content
        assert "测试研报" in content
        assert "龙虎榜" in content
        assert "限售解禁" in content
        assert "机器人概念" in content
        assert "A股决策委员会" in content
        assert "技术分析 Agent" in content
        assert "仓位" in content
        assert "关键价位" in content
        assert "催化因素" in content
        assert "交易计划卡片" in content
        assert "执行风控 Agent" in content
        assert "风控防御看板" in content
        assert "资金博弈溯源" in content

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

    def test_decision_score_and_risk_lines(self):
        service = DailyReportService(quote_service=object(), info_service=object(), recommender=object())

        assert service._decision_score({"signal_summary": "偏多信号（强）", "change_pct": 4}) == 88
        assert service._decision_score({"signal_summary": "偏空信号", "change_pct": -4}) == 22
        risk_lines = service._risk_lines({
            "lhb": {"period": "近一月", "times": 1, "net_amount": -1000000},
            "announcements": [{"title": "减持风险提示公告", "type": "风险提示"}],
        })

        assert any("龙虎榜" in line for line in risk_lines)
        assert any("公告关注" in line for line in risk_lines)

    def test_render_markdown_contains_llm_debate_when_present(self):
        service = DailyReportService(quote_service=object(), info_service=object(), recommender=object())
        content = service.render_markdown({
            "date": "2026-05-13",
            "generated_at": "2026-05-13 15:30:00",
            "market_indices": [],
            "recommendations": [],
            "extended_info": [],
            "watchlist": [{
                "symbol": "000001",
                "name": "平安银行",
                "price": 11.25,
                "change_pct": 1.2,
                "signal_summary": "偏多信号",
            }],
            "debates": {
                "000001": {
                    "enabled": True,
                    "bull": {"structured": {"核心论点": "资金与技术共振", "证据": ["主力净流入", "MACD金叉"]}},
                    "bear": {"structured": {"核心论点": "短线波动偏大", "风险": ["涨幅过快"]}},
                    "risk_manager": {"structured": {"最终裁决": "轻仓试探", "建议仓位": "1-2成", "置信度": "中", "核心理由": "等待回踩确认"}},
                }
            },
        })

        assert "LLM多空辩论" in content
        assert "多头：资金与技术共振" in content
        assert "空头：短线波动偏大" in content
        assert "风控裁决：轻仓试探" in content
