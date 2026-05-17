"""定时调度模块测试"""
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def scheduler_defaults(monkeypatch):
    """调度单元测试默认关闭日报，并清空自选股。"""
    monkeypatch.setattr("scheduler.DAILY_REPORT_ENABLED", False)
    monkeypatch.setattr("scheduler._load_watchlist_from_file", lambda: [])


@pytest.fixture
def sector_data():
    return {
        "算力租赁": {
            "短线": [
                {"symbol": "000977", "name": "浪潮信息", "latest_price": 45.12, "change_pct": 2.3},
                {"symbol": "603019", "name": "中科曙光", "latest_price": 39.88, "change_pct": 1.1},
            ],
            "长线": [
                {"symbol": "601138", "name": "工业富联", "latest_price": 28.66, "change_pct": -0.4},
            ],
        },
        "电力": {"短线": [], "长线": []},
        "苹果概念": {"短线": [], "长线": []},
        "特斯拉概念": {"短线": [], "长线": []},
    }


class TestSchedulerImport:

    def test_scheduler_imports_cleanly(self):
        """scheduler 模块可正常导入"""
        from scheduler import run_scheduled_analysis, start_scheduler, run_t1_plan_preheat
        assert callable(run_scheduled_analysis)
        assert callable(start_scheduler)
        assert callable(run_t1_plan_preheat)


class TestRunScheduledAnalysis:

    def test_t1_plan_preheat_calls_service_without_realtime_selection(self, monkeypatch):
        """T+1 预生成只调用推荐服务生成计划，不执行入场实时检查。"""
        fake_service = MagicMock()
        fake_service.run_t1_plan.return_value = {
            "recommended": [{"symbol": "002001"}],
            "generation_metrics": {"elapsed_seconds": 1.2},
        }
        monkeypatch.setattr("scheduler.T1_PLAN_STRATEGY", "多因子稳健型")
        monkeypatch.setattr("scheduler.T1_PLAN_SECTOR", "全部")
        monkeypatch.setattr("scheduler.T1_PLAN_NUM_STOCKS", 5)
        monkeypatch.setattr("scheduler.T1_PLAN_PREHEAT_KLINE", True)
        monkeypatch.setattr("scheduler.T1_PLAN_PREHEAT_EXTENDED_INFO", True)
        monkeypatch.setattr("recommendation_service.RecommendationService", lambda: fake_service)

        from scheduler import run_t1_plan_preheat
        plan = run_t1_plan_preheat()

        assert plan["recommended"][0]["symbol"] == "002001"
        fake_service.run_t1_plan.assert_called_once_with(
            "多因子稳健型",
            "全部",
            5,
            trigger="scheduler",
            preheat_kline=True,
            preheat_extended_info=True,
        )
        fake_service.check_entry_plan.assert_not_called()

    def test_no_notify_channels_skips_push(self, sector_data):
        """通知未开启时不调用发送"""
        with patch("stock_recommendation.StockRecommender") as mock_rec, \
             patch("scheduler.NOTIFY_ENABLED", False), \
             patch("scheduler.SECTOR_PUSH_ENABLED", True), \
             patch("scheduler.send_push") as mock_push:
            mock_rec.return_value.get_all_sector_recommendations.return_value = sector_data

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()

            mock_push.assert_not_called()
            mock_rec.return_value.get_all_sector_recommendations.assert_called_once_with(
                short_top_n=2,
                long_top_n=1,
            )

    def test_sector_failure_gracefully_skips_push(self):
        """板块推荐失败不崩溃"""
        with patch("stock_recommendation.StockRecommender") as mock_rec, \
             patch("scheduler.SECTOR_PUSH_ENABLED", True), \
             patch("scheduler.logger") as mock_logger:
            mock_rec.return_value.get_all_sector_recommendations.side_effect = Exception("fail")

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()

            assert mock_logger.warning.called

    def test_sends_sector_push_when_enabled(self, sector_data):
        """通知开启且有板块推荐时调用推送"""
        with patch("stock_recommendation.StockRecommender") as mock_rec, \
             patch("scheduler.NOTIFY_ENABLED", True), \
             patch("scheduler.SECTOR_PUSH_ENABLED", True), \
             patch("scheduler.send_push", return_value={"feishu": True}) as mock_push:
            mock_rec.return_value.get_all_sector_recommendations.return_value = sector_data

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()

            mock_push.assert_called_once()
            title, body = mock_push.call_args.args
            assert title.startswith("📊 每日选股报告")
            assert "板块策略推荐" in body
            assert "浪潮信息" in body

    def test_generic_recommendations_are_not_used(self, sector_data):
        """定时推送不再使用全市场推荐股补充内容"""
        with patch("stock_recommendation.StockRecommender") as mock_rec, \
             patch("scheduler.NOTIFY_ENABLED", True), \
             patch("scheduler.SECTOR_PUSH_ENABLED", True), \
             patch("scheduler.send_push", return_value={"feishu": True}):
            instance = mock_rec.return_value
            instance.get_all_sector_recommendations.return_value = sector_data

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()

            instance.get_recommended_stocks_cn.assert_not_called()
            instance.get_recommended_stocks_hk.assert_not_called()
            instance.get_recommended_stocks_us.assert_not_called()

    def test_daily_report_generated_and_pushed_when_enabled(self):
        """定时任务开启日报时生成并推送完整 Markdown 报告"""
        with patch("stock_recommendation.StockRecommender"), \
             patch("scheduler.NOTIFY_ENABLED", True), \
             patch("scheduler.SECTOR_PUSH_ENABLED", False), \
             patch("scheduler.DAILY_REPORT_ENABLED", True), \
             patch("scheduler.DAILY_REPORT_PUSH_ENABLED", True), \
             patch("scheduler.DAILY_REPORT_DIR", "tmp_reports"), \
             patch("scheduler.send_push", return_value={"wechat": True}) as mock_push, \
             patch("reports.daily_report_service.DailyReportService") as mock_report_service, \
             patch("scheduler.save_markdown_report", return_value={"dated": "tmp_reports/2026-05-13.md", "latest": "tmp_reports/latest.md"}):
            mock_report_service.return_value.generate_markdown.return_value = "# 每日股票分析报告"

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()

            mock_push.assert_called_once()
            assert mock_push.call_args.args[0].startswith("📄 每日完整分析报告")
            assert "报告文件" in mock_push.call_args.args[1]

    def test_daily_report_generate_only_when_push_disabled(self):
        """关闭日报推送时仍生成 Markdown 文件但不额外推送"""
        with patch("stock_recommendation.StockRecommender"), \
             patch("scheduler.NOTIFY_ENABLED", True), \
             patch("scheduler.SECTOR_PUSH_ENABLED", False), \
             patch("scheduler.DAILY_REPORT_ENABLED", True), \
             patch("scheduler.DAILY_REPORT_PUSH_ENABLED", False), \
             patch("scheduler.send_push", return_value={"wechat": True}) as mock_push, \
             patch("reports.daily_report_service.DailyReportService") as mock_report_service, \
             patch("scheduler.save_markdown_report", return_value={"dated": "tmp.md", "latest": "latest.md"}) as mock_save:
            mock_report_service.return_value.generate_markdown.return_value = "# 每日股票分析报告"

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()

            mock_save.assert_called_once()
            mock_push.assert_not_called()

    def test_daily_report_disabled_skips_generation(self, sector_data):
        """关闭每日报告时不生成报告"""
        with patch("stock_recommendation.StockRecommender") as mock_rec, \
             patch("scheduler.NOTIFY_ENABLED", True), \
             patch("scheduler.SECTOR_PUSH_ENABLED", True), \
             patch("scheduler.DAILY_REPORT_ENABLED", False), \
             patch("scheduler.send_push", return_value={"wechat": True}), \
             patch("reports.daily_report_service.DailyReportService") as mock_report_service:
            mock_rec.return_value.get_all_sector_recommendations.return_value = sector_data

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()

            mock_report_service.assert_not_called()

    def test_daily_report_failure_does_not_block_sector_push(self, sector_data):
        """日报生成失败不影响板块摘要推送"""
        with patch("stock_recommendation.StockRecommender") as mock_rec, \
             patch("scheduler.NOTIFY_ENABLED", True), \
             patch("scheduler.SECTOR_PUSH_ENABLED", True), \
             patch("scheduler.DAILY_REPORT_ENABLED", True), \
             patch("scheduler.send_push", return_value={"wechat": True}) as mock_push, \
             patch("reports.daily_report_service.DailyReportService") as mock_report_service:
            mock_rec.return_value.get_all_sector_recommendations.return_value = sector_data
            mock_report_service.return_value.generate_markdown.side_effect = Exception("boom")

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()

            mock_push.assert_called_once()

    def test_daily_report_runs_even_without_stock_reports(self):
        """没有选股摘要时仍生成并推送日报"""
        with patch("stock_recommendation.StockRecommender"), \
             patch("scheduler.NOTIFY_ENABLED", True), \
             patch("scheduler.SECTOR_PUSH_ENABLED", False), \
             patch("scheduler.DAILY_REPORT_ENABLED", True), \
             patch("scheduler.DAILY_REPORT_PUSH_ENABLED", True), \
             patch("scheduler.send_push", return_value={"wechat": True}) as mock_push, \
             patch("reports.daily_report_service.DailyReportService") as mock_report_service, \
             patch("scheduler.save_markdown_report", return_value={"dated": "tmp.md", "latest": "latest.md"}):
            mock_report_service.return_value.generate_markdown.return_value = "# 每日股票分析报告"

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()

            mock_push.assert_called_once()
            assert mock_push.call_args.args[0].startswith("📄 每日完整分析报告")


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


    def test_t1_preheat_schedule_setup_when_enabled(self):
        """开启 T1_PLAN_AUTO_ENABLED 时额外注册 T+1 预生成任务。"""
        with patch("scheduler.SCHEDULE_RUN_IMMEDIATELY", False), \
             patch("scheduler.SCHEDULE_TIME", "15:30"), \
             patch("scheduler.T1_PLAN_AUTO_ENABLED", True), \
             patch("scheduler.T1_PLAN_SCHEDULE_TIME", "15:45"), \
             patch("scheduler.schedule") as mock_schedule, \
             patch("scheduler.signal.signal"), \
             patch("scheduler.time.sleep", side_effect=StopIteration):
            from scheduler import start_scheduler
            try:
                start_scheduler()
            except StopIteration:
                pass
            at_calls = [call.args[0] for call in mock_schedule.every.return_value.day.at.call_args_list]
            assert "15:30" in at_calls
            assert "15:45" in at_calls


class TestWatchlistPriority:

    def test_load_watchlist_empty(self, monkeypatch):
        """无 watchlist.json → 返回空列表"""
        monkeypatch.setattr('scheduler._load_watchlist_from_file', lambda: [])
        from scheduler import _load_watchlist_from_file
        assert _load_watchlist_from_file() == []

    def test_load_watchlist_with_data(self, monkeypatch):
        """有 watchlist.json → 返回列表"""
        mock_data = [{'symbol': '000001', 'name': '平安银行', 'market': 'CN'}]
        monkeypatch.setattr('scheduler._load_watchlist_from_file', lambda: mock_data)
        from scheduler import _load_watchlist_from_file
        assert len(_load_watchlist_from_file()) == 1

    def test_run_with_watchlist(self, monkeypatch):
        """有自选股时 → 自选股摘要和板块推荐一起推送"""
        watchlist_data = [{'symbol': '000001', 'name': '平安银行', 'market': 'CN'}]
        monkeypatch.setattr('scheduler._load_watchlist_from_file', lambda: watchlist_data)
        monkeypatch.setattr('scheduler.NOTIFY_ENABLED', True)
        monkeypatch.setattr('scheduler.SECTOR_PUSH_ENABLED', True)
        monkeypatch.setattr('scheduler.DAILY_REPORT_ENABLED', False)
        mock_push = MagicMock(return_value={'feishu': True})
        monkeypatch.setattr('scheduler.send_push', mock_push)

        mock_rec = MagicMock()
        mock_rec.get_all_sector_recommendations.return_value = {
            "算力租赁": {"短线": [], "长线": []},
            "电力": {"短线": [], "长线": []},
            "苹果概念": {"短线": [], "长线": []},
            "特斯拉概念": {"短线": [], "长线": []},
        }
        monkeypatch.setattr('stock_recommendation.StockRecommender', lambda: mock_rec)

        monkeypatch.setattr(
            'watchlist.get_watchlist_summary',
            lambda watchlist: [{
                'symbol': '000001',
                'name': '平安银行',
                'price': 12.5,
                'change_pct': 1.2,
                'signal_summary': '偏多',
                'entry_hint': '回踩关注',
            }],
        )
        fake_info_service = MagicMock()
        fake_info_service.get_stock_extended_info.return_value = {
            "fund_flow": {"main_net_inflow": 1000000, "main_net_inflow_ratio": 1.1},
        }
        monkeypatch.setattr('data.services.info_service.StockInfoService', lambda: fake_info_service)

        from scheduler import run_scheduled_analysis
        run_scheduled_analysis()

        mock_push.assert_called_once()
        body = mock_push.call_args.args[1]
        assert "平安银行" in body
        assert "板块策略推荐" in body
        assert "交易计划卡片" in body
        assert "风控防御看板" in body
        assert "资金博弈溯源" in body


class TestSectorPushIntegration:

    def test_sector_disabled_skips_analysis(self):
        """SECTOR_PUSH_ENABLED=false 时不调用板块分析"""
        with patch("stock_recommendation.StockRecommender") as mock_rec, \
             patch("scheduler.SECTOR_PUSH_ENABLED", False), \
             patch("scheduler.NOTIFY_ENABLED", False):

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()

            mock_rec.return_value.get_all_sector_recommendations.assert_not_called()

    def test_sector_enabled_calls_analysis_with_configured_counts(self, sector_data):
        """SECTOR_PUSH_ENABLED=true 时按短线2/长线1调用板块分析"""
        with patch("stock_recommendation.StockRecommender") as mock_rec, \
             patch("scheduler.SECTOR_PUSH_ENABLED", True), \
             patch("scheduler.SECTOR_PUSH_SHORT_TOP_N", 2), \
             patch("scheduler.SECTOR_PUSH_LONG_TOP_N", 1), \
             patch("scheduler.NOTIFY_ENABLED", True), \
             patch("scheduler.send_push", return_value={"feishu": True}):
            mock_rec.return_value.get_all_sector_recommendations.return_value = sector_data

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()

            mock_rec.return_value.get_all_sector_recommendations.assert_called_once_with(
                short_top_n=2,
                long_top_n=1,
            )

    def test_sector_failure_does_not_block_daily_report(self):
        """板块分析失败时每日报告仍继续处理"""
        with patch("stock_recommendation.StockRecommender") as mock_rec, \
             patch("scheduler.SECTOR_PUSH_ENABLED", True), \
             patch("scheduler.NOTIFY_ENABLED", True), \
             patch("scheduler.DAILY_REPORT_ENABLED", True), \
             patch("scheduler.DAILY_REPORT_PUSH_ENABLED", True), \
             patch("scheduler.send_push", return_value={"feishu": True}) as mock_push, \
             patch("reports.daily_report_service.DailyReportService") as mock_report_service, \
             patch("scheduler.save_markdown_report", return_value={"dated": "tmp.md", "latest": "latest.md"}):
            mock_rec.return_value.get_all_sector_recommendations.side_effect = Exception("板块分析崩溃")
            mock_report_service.return_value.generate_markdown.return_value = "# 每日股票分析报告"

            from scheduler import run_scheduled_analysis
            run_scheduled_analysis()

            mock_push.assert_called_once()
            assert mock_push.call_args.args[0].startswith("📄 每日完整分析报告")
