"""定时调度模块测试"""
import pytest
from unittest.mock import patch, MagicMock


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
             patch("data_fetcher.StockDataFetcher"), \
             patch("scheduler.NOTIFY_ENABLED", True), \
             patch("scheduler.send_push", return_value={"wechat": True}) as mock_push:
            mock_rec.return_value.get_recommended_stocks_cn.return_value = [sample_stock]
            mock_rec.return_value.get_recommended_stocks_hk.return_value = []
            mock_rec.return_value.get_recommended_stocks_us.return_value = []

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()

            mock_push.assert_called_once()

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
