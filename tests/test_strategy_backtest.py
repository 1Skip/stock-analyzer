from datetime import datetime, timedelta
import json

from strategy_backtest import STRATEGIES, StrategyBacktestAdapter, _StrategyOutcomeQuoteService


class FakeStrategyHistoryService:
    def __init__(self):
        trade_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        self.rows = [
            {
                "strategy": strategy,
                "sector": "全部",
                "plan_for_trade_date": trade_date,
                "plan": {
                    "strategy": strategy,
                    "sector": "全部",
                    "plan_for_trade_date": trade_date,
                    "recommended": [{"symbol": f"00000{index + 1}", "name": strategy}],
                },
            }
            for index, strategy in enumerate(STRATEGIES)
        ]

    def list_t1_plan_history(self, limit=5000):
        return self.rows[:limit]

    def evaluate_t1_plan_outcomes(self, plan):
        stock = plan["recommended"][0]
        return {
            "items": [
                {
                    "symbol": stock["symbol"],
                    "name": stock["name"],
                    "status": "completed",
                    "returns": {"1d": 1.0, "5d": 2.0, "20d": -1.0},
                }
            ]
        }


def test_strategy_backtest_includes_all_current_strategies():
    result = StrategyBacktestAdapter(FakeStrategyHistoryService()).run("1y")

    assert [row["strategy"] for row in result["strategies"]] == list(STRATEGIES)
    assert result["summary"]["strategies_with_plans"] == len(STRATEGIES)
    assert result["summary"]["plan_count"] == len(STRATEGIES)
    assert result["summary"]["completed_count"] == len(STRATEGIES)
    assert all(row["avg_5d_return_pct"] == 2.0 for row in result["strategies"])
    assert all(row["win_rate_20d_pct"] == 0.0 for row in result["strategies"])


def test_strategy_backtest_deduplicates_exact_plan_reruns():
    service = FakeStrategyHistoryService()
    service.rows.append({**service.rows[0], "generated_at": "later rerun"})

    result = StrategyBacktestAdapter(service).run("1y")

    assert result["summary"]["plan_count"] == len(STRATEGIES)
    assert result["summary"]["completed_count"] == len(STRATEGIES)


def test_strategy_backtest_marks_requested_history_gap():
    result = StrategyBacktestAdapter(FakeStrategyHistoryService()).run("5y")

    assert result["coverage"]["is_complete"] is False
    assert result["coverage"]["status"] == "partial"
    assert result["requested_start"] < result["coverage"]["actual_start"]


def test_strategy_backtest_prefers_latest_complete_real_kline_cache(tmp_path):
    quote_service = _StrategyOutcomeQuoteService(None)
    quote_service.cache_dir = tmp_path

    def write_cache(period, dates):
        payload = {
            "columns": ["close"],
            "index": dates,
            "data": [[10.0 + index] for index in range(len(dates))],
        }
        path = tmp_path / f"CN_000001_{period}_1d_{dates[-1]}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    write_cache("6mo", ["2026-06-01", "2026-06-02"])
    expected = write_cache("5y", ["2026-07-16", "2026-07-17"])

    result = quote_service.get_stock_data("000001", period="6mo", market="CN")

    assert result.index.max().strftime("%Y-%m-%d") == "2026-07-17"
    assert result.attrs["cache_file"] == expected.name


def test_backtest_page_uses_strategy_validation_as_primary_view():
    from pathlib import Path

    source = Path("backtest_ui.py").read_text(encoding="utf-8")

    assert 'st.tabs(["五策略真实验证", "单股信号诊断"])' in source
    assert 'st.form_submit_button("验证全部策略"' in source
    assert "StrategyBacktestAdapter().run(period=period)" in source
    assert "def _render_single_stock_signal_diagnostic" in source
