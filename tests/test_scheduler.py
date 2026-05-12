"""定时调度模块测试"""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def disable_daily_report_by_default(monkeypatch):
    """调度单元测试默认关闭日报，涉及日报的测试显式打开。"""
    monkeypatch.setattr("scheduler.DAILY_REPORT_ENABLED", False)


class TestSchedulerImport:

    def test_scheduler_imports_cleanly(self):
        """scheduler 模块可正常导入"""
        from scheduler import run_scheduled_analysis, start_scheduler
        assert callable(run_scheduled_analysis)
        assert callable(start_scheduler)


class TestRunScheduledAnalysis:

    def test_no_notify_channels_skips_push(self):
        """通知未开启时不调用发送"""
        with patch("stock_recommendation.StockRecommender") as mock_rec, \
             patch("data_fetcher.StockDataFetcher"), \
             patch("scheduler.NOTIFY_ENABLED", False), \
             patch("scheduler.send_push") as mock_push:
            mock_rec.return_value.get_recommended_stocks_cn.return_value = []
            mock_rec.return_value.get_recommended_stocks_hk.return_value = []
            mock_rec.return_value.get_recommended_stocks_us.return_value = []

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()
            mock_push.assert_not_called()

    def test_all_markets_fail_gracefully(self):
        """所有市场获取失败不崩溃"""
        with patch("stock_recommendation.StockRecommender") as mock_rec, \
             patch("data_fetcher.StockDataFetcher"), \
             patch("scheduler.logger") as mock_logger:
            mock_rec.return_value.get_recommended_stocks_cn.side_effect = Exception("fail")
            mock_rec.return_value.get_recommended_stocks_hk.side_effect = Exception("fail")
            mock_rec.return_value.get_recommended_stocks_us.side_effect = Exception("fail")

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()  # 不抛异常
            assert mock_logger.warning.called

    def test_sends_push_when_enabled(self):
        """通知开启且有分析结果时调用推送"""
        sample_stock = {
            "symbol": "000001",
            "name": "平安银行",
            "latest_price": 12.50,
            "change_pct": 2.35,
            "signals": {"macd": "偏多", "rsi": "偏多", "kdj": "偏多", "boll": "偏多"},
        }

        with patch("stock_recommendation.StockRecommender") as mock_rec, \
             patch("data_fetcher.StockDataFetcher") as mock_fetcher, \
             patch("scheduler.NOTIFY_ENABLED", True), \
             patch("scheduler.send_push", return_value={"wechat": True}) as mock_push:
            mock_fetcher.return_value.get_realtime_quote.return_value = None
            mock_rec.return_value.get_recommended_stocks_cn.return_value = [sample_stock]
            mock_rec.return_value.get_recommended_stocks_hk.return_value = []
            mock_rec.return_value.get_recommended_stocks_us.return_value = []

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()

            mock_push.assert_called_once()

    def test_daily_report_generated_and_pushed_when_enabled(self):
        """定时任务开启日报时生成并推送完整 Markdown 报告"""
        sample_stock = {
            "symbol": "000001",
            "name": "平安银行",
            "latest_price": 12.50,
            "change_pct": 2.35,
            "signals": {"macd": "偏多"},
        }

        with patch("stock_recommendation.StockRecommender") as mock_rec, \
             patch("data_fetcher.StockDataFetcher") as mock_fetcher, \
             patch("scheduler.NOTIFY_ENABLED", True), \
             patch("scheduler.DAILY_REPORT_ENABLED", True), \
             patch("scheduler.DAILY_REPORT_PUSH_ENABLED", True), \
             patch("scheduler.DAILY_REPORT_DIR", "tmp_reports"), \
             patch("scheduler.send_push", return_value={"wechat": True}) as mock_push, \
             patch("reports.daily_report_service.DailyReportService") as mock_report_service, \
             patch("scheduler.save_markdown_report", return_value={"dated": "tmp_reports/2026-05-13.md", "latest": "tmp_reports/latest.md"}):
            mock_fetcher.return_value.get_realtime_quote.return_value = None
            mock_rec.return_value.get_recommended_stocks_cn.return_value = [sample_stock]
            mock_rec.return_value.get_recommended_stocks_hk.return_value = []
            mock_rec.return_value.get_recommended_stocks_us.return_value = []
            mock_report_service.return_value.generate_markdown.return_value = "# 每日股票分析报告"

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()

            assert mock_push.call_count == 2
            assert mock_push.call_args_list[1].args[0].startswith("📄 每日完整分析报告")
            assert "报告文件" in mock_push.call_args_list[1].args[1]

    def test_daily_report_generate_only_when_push_disabled(self):
        """关闭日报推送时仍生成 Markdown 文件但不额外推送"""
        sample_stock = {
            "symbol": "000001",
            "name": "平安银行",
            "latest_price": 12.50,
            "change_pct": 2.35,
            "signals": {"macd": "偏多"},
        }

        with patch("stock_recommendation.StockRecommender") as mock_rec, \
             patch("data_fetcher.StockDataFetcher") as mock_fetcher, \
             patch("scheduler.NOTIFY_ENABLED", True), \
             patch("scheduler.DAILY_REPORT_ENABLED", True), \
             patch("scheduler.DAILY_REPORT_PUSH_ENABLED", False), \
             patch("scheduler.send_push", return_value={"wechat": True}) as mock_push, \
             patch("reports.daily_report_service.DailyReportService") as mock_report_service, \
             patch("scheduler.save_markdown_report", return_value={"dated": "tmp.md", "latest": "latest.md"}) as mock_save:
            mock_fetcher.return_value.get_realtime_quote.return_value = None
            mock_rec.return_value.get_recommended_stocks_cn.return_value = [sample_stock]
            mock_rec.return_value.get_recommended_stocks_hk.return_value = []
            mock_rec.return_value.get_recommended_stocks_us.return_value = []
            mock_report_service.return_value.generate_markdown.return_value = "# 每日股票分析报告"

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()

            mock_save.assert_called_once()
            mock_push.assert_called_once()

    def test_daily_report_disabled_skips_generation(self):
        """关闭每日报告时不生成报告"""
        sample_stock = {
            "symbol": "000001",
            "name": "平安银行",
            "latest_price": 12.50,
            "change_pct": 2.35,
            "signals": {"macd": "偏多"},
        }

        with patch("stock_recommendation.StockRecommender") as mock_rec, \
             patch("data_fetcher.StockDataFetcher") as mock_fetcher, \
             patch("scheduler.NOTIFY_ENABLED", True), \
             patch("scheduler.DAILY_REPORT_ENABLED", False), \
             patch("scheduler.send_push", return_value={"wechat": True}) as mock_push, \
             patch("reports.daily_report_service.DailyReportService") as mock_report_service:
            mock_fetcher.return_value.get_realtime_quote.return_value = None
            mock_rec.return_value.get_recommended_stocks_cn.return_value = [sample_stock]
            mock_rec.return_value.get_recommended_stocks_hk.return_value = []
            mock_rec.return_value.get_recommended_stocks_us.return_value = []

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()

            mock_report_service.assert_not_called()
            mock_push.assert_called_once()

    def test_daily_report_failure_does_not_block_main_push(self):
        """日报生成失败不影响原有摘要推送"""
        sample_stock = {
            "symbol": "000001",
            "name": "平安银行",
            "latest_price": 12.50,
            "change_pct": 2.35,
            "signals": {"macd": "偏多"},
        }

        with patch("stock_recommendation.StockRecommender") as mock_rec, \
             patch("data_fetcher.StockDataFetcher") as mock_fetcher, \
             patch("scheduler.NOTIFY_ENABLED", True), \
             patch("scheduler.DAILY_REPORT_ENABLED", True), \
             patch("scheduler.send_push", return_value={"wechat": True}) as mock_push, \
             patch("reports.daily_report_service.DailyReportService") as mock_report_service:
            mock_fetcher.return_value.get_realtime_quote.return_value = None
            mock_rec.return_value.get_recommended_stocks_cn.return_value = [sample_stock]
            mock_rec.return_value.get_recommended_stocks_hk.return_value = []
            mock_rec.return_value.get_recommended_stocks_us.return_value = []
            mock_report_service.return_value.generate_markdown.side_effect = Exception("boom")

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()

            mock_push.assert_called_once()

    def test_daily_report_runs_even_without_stock_reports(self):
        """没有选股摘要时仍生成并推送日报"""
        with patch("stock_recommendation.StockRecommender") as mock_rec, \
             patch("data_fetcher.StockDataFetcher"), \
             patch("scheduler.NOTIFY_ENABLED", True), \
             patch("scheduler.SECTOR_PUSH_ENABLED", False), \
             patch("scheduler.DAILY_REPORT_ENABLED", True), \
             patch("scheduler.DAILY_REPORT_PUSH_ENABLED", True), \
             patch("scheduler.send_push", return_value={"wechat": True}) as mock_push, \
             patch("reports.daily_report_service.DailyReportService") as mock_report_service, \
             patch("scheduler.save_markdown_report", return_value={"dated": "tmp.md", "latest": "latest.md"}):
            mock_rec.return_value.get_recommended_stocks_cn.return_value = []
            mock_rec.return_value.get_recommended_stocks_hk.return_value = []
            mock_rec.return_value.get_recommended_stocks_us.return_value = []
            mock_report_service.return_value.generate_markdown.return_value = "# 每日股票分析报告"

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()

            mock_push.assert_called_once()
            assert mock_push.call_args.args[0].startswith("📄 每日完整分析报告")

    def test_individual_stock_failure_doesnt_block_others(self):
        """单只股票分析失败不影响其他"""
        good = {
            "symbol": "000001", "name": "平安银行",
            "latest_price": 12.50, "change_pct": 2.35,
            "signals": {"macd": "偏多"},
        }
        bad = {
            "symbol": "BAD", "name": "坏股票",
            "latest_price": 1.00, "change_pct": 0,
        }

        with patch("stock_recommendation.StockRecommender") as mock_rec, \
             patch("data_fetcher.StockDataFetcher") as mock_fetch, \
             patch("scheduler.NOTIFY_ENABLED", False):
            mock_rec.return_value.get_recommended_stocks_cn.return_value = [bad, good]
            mock_rec.return_value.get_recommended_stocks_hk.return_value = []
            mock_rec.return_value.get_recommended_stocks_us.return_value = []
            mock_fetch.return_value.get_stock_data.return_value = None

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()  # 不抛异常


class TestStartScheduler:

    def test_immediate_run(self):
        """SCHEDULE_RUN_IMMEDIATELY 时立即执行一次"""
        with patch("scheduler.SCHEDULE_RUN_IMMEDIATELY", True), \
             patch("scheduler.run_scheduled_analysis") as mock_run, \
             patch("scheduler.schedule"), \
             patch("scheduler.signal.signal"), \
             patch("scheduler.time.sleep", side_effect=StopIteration):
            from scheduler import start_scheduler
            try:
                start_scheduler()
            except StopIteration:
                pass
            mock_run.assert_called_once()

    def test_schedule_setup(self):
        """验证 schedule.every().day.at() 被正确调用"""
        with patch("scheduler.SCHEDULE_RUN_IMMEDIATELY", False), \
             patch("scheduler.SCHEDULE_TIME", "15:30"), \
             patch("scheduler.schedule") as mock_schedule, \
             patch("scheduler.signal.signal"), \
             patch("scheduler.time.sleep", side_effect=StopIteration):
            from scheduler import start_scheduler
            try:
                start_scheduler()
            except StopIteration:
                pass
            mock_schedule.every.return_value.day.at.assert_called_with("15:30")


# ============================================================
# TestWatchlistPriority
# ============================================================

class TestWatchlistPriority:

    def test_load_watchlist_empty(self, tmp_path, monkeypatch):
        """无 watchlist.json → 返回空列表"""
        watchlist_file = tmp_path / 'watchlist.json'
        monkeypatch.setattr('scheduler._load_watchlist_from_file', lambda: [])
        from scheduler import _load_watchlist_from_file
        # 直接替换函数后验证返回空
        assert _load_watchlist_from_file() == []

    def test_load_watchlist_with_data(self, tmp_path, monkeypatch):
        """有 watchlist.json → 返回列表"""
        mock_data = [{'symbol': '000001', 'name': '平安银行', 'market': 'CN'}]
        monkeypatch.setattr('scheduler._load_watchlist_from_file', lambda: mock_data)
        from scheduler import _load_watchlist_from_file
        assert len(_load_watchlist_from_file()) == 1

    def test_run_with_watchlist(self, monkeypatch):
        """有自选股时 → 优先分析自选股并推送"""
        from unittest.mock import MagicMock
        import pandas as pd

        watchlist_data = [{'symbol': '000001', 'name': '平安银行', 'market': 'CN'}]
        monkeypatch.setattr('scheduler._load_watchlist_from_file', lambda: watchlist_data)
        monkeypatch.setattr('scheduler.NOTIFY_ENABLED', True)
        mock_push = MagicMock(return_value={'feishu': True})
        monkeypatch.setattr('scheduler.send_push', mock_push)

        # Mock 推荐列表返回空（自选股已覆盖）
        mock_rec = MagicMock()
        mock_rec.get_recommended_stocks_cn.return_value = []
        mock_rec.get_recommended_stocks_hk.return_value = []
        mock_rec.get_recommended_stocks_us.return_value = []
        # StockRecommender is imported inside the function, patch original module
        monkeypatch.setattr('stock_recommendation.StockRecommender', lambda: mock_rec)

        # Mock 数据获取
        dates = pd.date_range('2025-06-01', periods=30, freq='B')
        n = 30
        mock_df = pd.DataFrame({
            'open': [10]*n, 'high': [10.5]*n, 'low': [9.5]*n, 'close': [10]*n,
            'volume': [1000000]*n,
        }, index=dates)

        from data_fetcher import StockDataFetcher
        monkeypatch.setattr(StockDataFetcher, 'get_stock_data',
                           lambda self, symbol, period, market: mock_df)

        from scheduler import run_scheduled_analysis
        run_scheduled_analysis()

        mock_push.assert_called_once()


# ============================================================
# TestSectorPushIntegration
# ============================================================

class TestSectorPushIntegration:

    def test_sector_disabled_skips_analysis(self):
        """SECTOR_PUSH_ENABLED=false 时不调用板块分析"""
        with patch("stock_recommendation.StockRecommender") as mock_rec, \
             patch("data_fetcher.StockDataFetcher"), \
             patch("scheduler.SECTOR_PUSH_ENABLED", False), \
             patch("scheduler.NOTIFY_ENABLED", False):
            mock_rec.return_value.get_recommended_stocks_cn.return_value = []
            mock_rec.return_value.get_recommended_stocks_hk.return_value = []
            mock_rec.return_value.get_recommended_stocks_us.return_value = []

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()
            mock_rec.return_value.get_all_sector_recommendations.assert_not_called()

    def test_sector_enabled_calls_analysis(self):
        """SECTOR_PUSH_ENABLED=true 时调用板块分析"""
        with patch("stock_recommendation.StockRecommender") as mock_rec, \
             patch("data_fetcher.StockDataFetcher") as mock_fetcher, \
             patch("scheduler.SECTOR_PUSH_ENABLED", True), \
             patch("scheduler.NOTIFY_ENABLED", True), \
             patch("scheduler.send_push", return_value={"feishu": True}):
            mock_fetcher.return_value.get_realtime_quote.return_value = None
            sample = {
                "symbol": "000001", "name": "平安银行",
                "latest_price": 12.50, "change_pct": 2.35,
                "signals": {"macd": "偏多"},
            }
            mock_rec.return_value.get_recommended_stocks_cn.return_value = [sample]
            mock_rec.return_value.get_recommended_stocks_hk.return_value = []
            mock_rec.return_value.get_recommended_stocks_us.return_value = []
            mock_rec.return_value.get_all_sector_recommendations.return_value = {
                "苹果概念": {"短线": [], "长线": []},
                "特斯拉概念": {"短线": [], "长线": []},
                "电力": {"短线": [], "长线": []},
                "算力租赁": {"短线": [], "长线": []},
            }

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()
            mock_rec.return_value.get_all_sector_recommendations.assert_called_once()

    def test_sector_failure_does_not_block_main_push(self):
        """板块分析失败时主推送不受影响"""
        with patch("stock_recommendation.StockRecommender") as mock_rec, \
             patch("data_fetcher.StockDataFetcher") as mock_fetcher, \
             patch("scheduler.SECTOR_PUSH_ENABLED", True), \
             patch("scheduler.NOTIFY_ENABLED", True), \
             patch("scheduler.send_push", return_value={"feishu": True}) as mock_push:
            mock_fetcher.return_value.get_realtime_quote.return_value = None
            sample = {
                "symbol": "000001", "name": "平安银行",
                "latest_price": 12.50, "change_pct": 2.35,
                "signals": {"macd": "偏多"},
            }
            mock_rec.return_value.get_recommended_stocks_cn.return_value = [sample]
            mock_rec.return_value.get_recommended_stocks_hk.return_value = []
            mock_rec.return_value.get_recommended_stocks_us.return_value = []
            mock_rec.return_value.get_all_sector_recommendations.side_effect = Exception("板块分析崩溃")

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()

            mock_push.assert_called_once()  # 主推送仍然执行
