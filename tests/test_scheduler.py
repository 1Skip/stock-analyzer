"""定时调度模块测试。"""
from unittest.mock import MagicMock, patch
import json


import pytest


@pytest.fixture(autouse=True)
def scheduler_defaults(monkeypatch):
    """调度单元测试默认关闭日报，并清空自选股。"""
    monkeypatch.setattr("scheduler.DAILY_REPORT_ENABLED", False)
    monkeypatch.setattr("scheduler._load_watchlist_from_file", lambda: [])


class TestSchedulerImport:

    def test_scheduler_imports_cleanly(self):
        from scheduler import run_scheduled_analysis, run_t1_plan_preheat, start_scheduler

        assert callable(run_scheduled_analysis)
        assert callable(run_t1_plan_preheat)
        assert callable(start_scheduler)


class TestT1PlanSchedule:

    def test_t1_targets_use_short_long_four_sectors_and_aggressive_steady_full_market(self, monkeypatch):
        import scheduler

        monkeypatch.setattr(
            scheduler,
            "T1_PLAN_STRATEGIES",
            ["短线", "长线", "多因子稳健型", "激进突破型"],
        )
        monkeypatch.setattr(
            scheduler,
            "T1_PLAN_SECTORS",
            ["苹果概念", "特斯拉概念", "电力", "算力租赁"],
        )
        monkeypatch.setattr(scheduler, "T1_PLAN_SECTOR", "苹果概念")

        assert scheduler._iter_t1_plan_targets() == [
            ("短线", "苹果概念"),
            ("短线", "特斯拉概念"),
            ("短线", "电力"),
            ("短线", "算力租赁"),
            ("长线", "苹果概念"),
            ("长线", "特斯拉概念"),
            ("长线", "电力"),
            ("长线", "算力租赁"),
            ("多因子稳健型", "全部"),
            ("激进突破型", "全部"),
        ]

    def test_t1_plan_preheat_calls_configured_targets_without_realtime_entry_check(self, monkeypatch):
        fake_service = MagicMock()
        fake_service.run_t1_plan.side_effect = lambda strategy, sector, *_args, **_kwargs: {
            "strategy": strategy,
            "sector": sector,
            "recommended": [{"symbol": "002001"}],
            "generation_metrics": {"elapsed_seconds": 1.2},
        }
        monkeypatch.setattr("scheduler.T1_PLAN_STRATEGIES", ["短线", "长线", "多因子稳健型", "激进突破型"])
        monkeypatch.setattr("scheduler.T1_PLAN_SECTORS", ["苹果概念", "特斯拉概念", "电力", "算力租赁"])
        monkeypatch.setattr("scheduler.T1_PLAN_SECTOR", "苹果概念")
        monkeypatch.setattr("scheduler.T1_PLAN_NUM_STOCKS", 5)
        monkeypatch.setattr("scheduler.T1_PLAN_PREHEAT_KLINE", True)
        monkeypatch.setattr("scheduler.T1_PLAN_PREHEAT_EXTENDED_INFO", True)
        monkeypatch.setattr("scheduler.T1_PLAN_STRATEGY_TIMEOUT_SECONDS", 0)
        monkeypatch.setattr("recommendation_service.RecommendationService", lambda: fake_service)

        from scheduler import run_t1_plan_preheat

        plans = run_t1_plan_preheat()

        assert fake_service.run_t1_plan.call_count == 10
        assert plans["短线:苹果概念"]["recommended"][0]["symbol"] == "002001"
        assert plans["长线:算力租赁"]["recommended"][0]["symbol"] == "002001"
        assert plans["多因子稳健型:全部"]["recommended"][0]["symbol"] == "002001"
        assert plans["激进突破型:全部"]["recommended"][0]["symbol"] == "002001"
        for call in fake_service.run_t1_plan.call_args_list:
            assert call.args[2:3] == (5,)
            assert call.kwargs == {
                "trigger": "scheduler",
                "preheat_kline": True,
                "preheat_extended_info": True,
            }
        fake_service.check_entry_plan.assert_not_called()

    def test_t1_plan_preheat_writes_status_without_changing_strategy_call(self, monkeypatch, tmp_path):
        import scheduler

        status_path = tmp_path / "scheduler_status.json"
        fake_service = MagicMock()
        fake_service.run_t1_plan.return_value = {
            "status": "success",
            "strategy": "短线",
            "sector": "全部",
            "recommended": [{"symbol": "002001"}, {"symbol": "002002"}],
            "generation_metrics": {"elapsed_seconds": 1.2},
            "cache_key": "t1:short:all:5",
        }
        monkeypatch.setattr(scheduler, "SCHEDULER_STATUS_PATH", status_path)
        monkeypatch.setattr(scheduler, "T1_PLAN_STRATEGIES", ["短线"])
        monkeypatch.setattr(scheduler, "T1_PLAN_SECTORS", ["全部"])
        monkeypatch.setattr(scheduler, "T1_PLAN_NUM_STOCKS", 5)
        monkeypatch.setattr(scheduler, "T1_PLAN_PREHEAT_KLINE", True)
        monkeypatch.setattr(scheduler, "T1_PLAN_PREHEAT_EXTENDED_INFO", True)
        monkeypatch.setattr(scheduler, "T1_PLAN_STRATEGY_TIMEOUT_SECONDS", 0)
        monkeypatch.setattr("recommendation_service.RecommendationService", lambda: fake_service)

        plans = scheduler.run_t1_plan_preheat()

        assert plans["短线:全部"]["recommended"][0]["symbol"] == "002001"
        fake_service.run_t1_plan.assert_called_once_with(
            "短线",
            "全部",
            5,
            trigger="scheduler",
            preheat_kline=True,
            preheat_extended_info=True,
        )
        status = json.loads(status_path.read_text(encoding="utf-8"))
        target = status["t1_preheat"]["targets"]["短线:全部"]
        assert status["t1_preheat"]["status"] == "success"
        assert target["recommended_count"] == 2
        assert target["cache_key"] == "t1:short:all:5"

    def test_t1_plan_preheat_returns_timeout_without_realtime_selection(self, monkeypatch):
        import subprocess
        import scheduler

        class SlowProcess:
            pid = 12345
            returncode = None

            def communicate(self, timeout=None):
                raise subprocess.TimeoutExpired(cmd="t1", timeout=timeout)

            def poll(self):
                return None

            def wait(self, timeout=None):
                return None

        monkeypatch.setattr(scheduler, "T1_PLAN_STRATEGY_TIMEOUT_SECONDS", 1)
        monkeypatch.setattr(scheduler, "T1_PLAN_PREHEAT_KLINE", True)
        monkeypatch.setattr(scheduler, "T1_PLAN_PREHEAT_EXTENDED_INFO", True)
        monkeypatch.setattr(scheduler.subprocess, "Popen", lambda *args, **kwargs: SlowProcess())
        monkeypatch.setattr(scheduler, "_terminate_process_tree", lambda process: None)

        plan = scheduler._run_t1_plan_strategy_with_timeout(
            service=MagicMock(),
            strategy="多因子稳健型",
            sector="全部",
            num_stocks=5,
        )

        assert plan["status"] == "timeout"
        assert plan["recommended"] == []
        assert plan["generation_metrics"]["realtime_used_for_selection"] is False
        assert plan["generation_metrics"]["scan_scope_changed"] is False


class TestRunScheduledAnalysis:

    def test_no_watchlist_and_no_daily_report_sends_nothing(self):
        from scheduler import run_scheduled_analysis

        run_scheduled_analysis()

    def test_daily_report_generated_locally(self):
        with patch("scheduler.DAILY_REPORT_ENABLED", True), \
             patch("scheduler.DAILY_REPORT_DIR", "tmp_reports"), \
             patch("reports.daily_report_service.DailyReportService") as mock_report_service, \
             patch("scheduler.save_markdown_report", return_value={"dated": "tmp_reports/2026-05-20.md", "latest": "tmp_reports/latest.md"}) as mock_save:
            mock_report_service.return_value.generate_markdown.return_value = "# ????????"

            from scheduler import run_scheduled_analysis

            run_scheduled_analysis()

            mock_save.assert_called_once()

    def test_watchlist_summary_builds_without_online_push(self, monkeypatch):
        watchlist_data = [{"symbol": "000001", "name": "????", "market": "CN"}]
        monkeypatch.setattr("scheduler._load_watchlist_from_file", lambda: watchlist_data)
        monkeypatch.setattr("scheduler.DAILY_REPORT_ENABLED", False)
        monkeypatch.setattr(
            "watchlist.get_watchlist_summary",
            lambda watchlist: [{
                "symbol": "000001",
                "name": "????",
                "price": 12.5,
                "change_pct": 1.2,
                "signal_summary": "??",
                "entry_hint": "????",
                "indicators": {},
            }],
        )
        fake_info_service = MagicMock()
        fake_info_service.get_stock_extended_info.return_value = {
            "fund_flow": {"main_net_inflow": 1000000, "main_net_inflow_ratio": 1.1},
        }
        monkeypatch.setattr("data.services.info_service.StockInfoService", lambda: fake_info_service)

        from scheduler import run_scheduled_analysis

        run_scheduled_analysis()

        fake_info_service.get_stock_extended_info.assert_called_once()

    def test_immediate_run(self):
        with patch("scheduler.SCHEDULE_RUN_IMMEDIATELY", True), \
             patch("scheduler._acquire_pid_lock", return_value=1), \
             patch("scheduler._release_pid_lock"), \
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
        with patch("scheduler.SCHEDULE_RUN_IMMEDIATELY", False), \
             patch("scheduler.SCHEDULE_TIME", "15:30"), \
             patch("scheduler.T1_PLAN_AUTO_ENABLED", False), \
             patch("scheduler._acquire_pid_lock", return_value=1), \
             patch("scheduler._release_pid_lock"), \
             patch("scheduler.schedule") as mock_schedule, \
             patch("scheduler.signal.signal"), \
             patch("scheduler.time.sleep", side_effect=StopIteration):
            from scheduler import start_scheduler

            try:
                start_scheduler()
            except StopIteration:
                pass

            mock_schedule.every.return_value.day.at.assert_called_with("15:30")

    def test_t1_preheat_schedule_setup_enabled_by_default(self):
        with patch("scheduler.SCHEDULE_RUN_IMMEDIATELY", False), \
             patch("scheduler.SCHEDULE_TIME", "15:30"), \
             patch("scheduler.T1_PLAN_SCHEDULE_TIME", "15:45"), \
             patch("scheduler._acquire_pid_lock", return_value=1), \
             patch("scheduler._release_pid_lock"), \
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

    def test_start_scheduler_skips_when_instance_lock_exists(self):
        with patch("scheduler._acquire_pid_lock", return_value=None), \
             patch("scheduler.schedule") as mock_schedule:
            from scheduler import start_scheduler

            start_scheduler()

            mock_schedule.every.assert_not_called()
