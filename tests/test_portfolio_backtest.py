import pandas as pd

from portfolio_backtest import PortfolioBacktestEngine
from portfolio_risk import PortfolioRiskLimits


class _StaticCorporateActionService:
    def __init__(self, events=None):
        self.events = list(events or [])

    def get_due_events(self, symbol, *, as_of_date, held_since=None):
        events = [
            event for event in self.events
            if event.get("symbol") == symbol
            and str(event.get("effective_date") or "") <= as_of_date
            and (
                not held_since
                or str(event.get("record_date") or event.get("effective_date") or "") >= held_since
            )
        ]
        return {
            "status": "ok",
            "source": "测试真实接口夹具",
            "cache_hit": False,
            "events": events,
            "due_event_count": len(events),
            "errors": [],
        }


def _frame(rows):
    frame = pd.DataFrame(rows).set_index("date")
    frame.index = pd.to_datetime(frame.index)
    return frame


def _plan(symbol, plan_date, *, strategy="实验策略", industry="电力", stop=9.5, target=10.8):
    return {
        "strategy": strategy,
        "strategy_version": "test",
        "sector": "全部",
        "plan_for_trade_date": plan_date,
        "recommended": [
            {
                "symbol": symbol,
                "name": symbol,
                "industry": industry,
                "trade_plan": {
                    "buy_zone_low": 9.8,
                    "buy_zone_high": 10.2,
                    "stop_loss": stop,
                    "take_profit_1": target,
                    "max_holding_days": 5,
                },
            }
        ],
    }


def _risk_limits():
    return PortfolioRiskLimits(
        max_drawdown_pct=50,
        max_daily_loss_pct=50,
        max_industry_exposure_pct=100,
        max_order_participation_pct=5,
        max_data_age_days=5,
    )


def test_portfolio_backtest_replays_overlapping_positions_cash_and_benchmark():
    frames = {
        "600001": _frame([
            {"date": "2026-06-30", "open": 10, "high": 10.1, "low": 9.9, "close": 10, "volume": 10_000_000},
            {"date": "2026-07-01", "open": 10, "high": 10.3, "low": 9.9, "close": 10.1, "volume": 10_000_000},
            {"date": "2026-07-02", "open": 10.2, "high": 10.5, "low": 10.0, "close": 10.4, "volume": 10_000_000},
            {"date": "2026-07-03", "open": 10.5, "high": 10.9, "low": 10.4, "close": 10.8, "volume": 10_000_000},
            {"date": "2026-07-04", "open": 10.8, "high": 10.9, "low": 10.7, "close": 10.8, "volume": 10_000_000},
        ]),
        "000001": _frame([
            {"date": "2026-07-01", "open": 10, "high": 10.1, "low": 9.9, "close": 10, "volume": 10_000_000},
            {"date": "2026-07-02", "open": 10, "high": 10.2, "low": 9.9, "close": 10.1, "volume": 10_000_000},
            {"date": "2026-07-03", "open": 10.2, "high": 10.4, "low": 10.0, "close": 10.3, "volume": 10_000_000},
            {"date": "2026-07-04", "open": 10.4, "high": 10.9, "low": 10.3, "close": 10.8, "volume": 10_000_000},
        ]),
    }
    benchmark = pd.DataFrame(
        {"close": [4000, 4040, 4080, 4120]},
        index=pd.to_datetime(["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04"]),
    )
    benchmark.attrs["data_source"] = "测试真实接口夹具"
    engine = PortfolioBacktestEngine(
        initial_cash=100_000,
        max_positions=2,
        position_pct=0.4,
        risk_limits=_risk_limits(),
        corporate_action_service=_StaticCorporateActionService(),
    )

    result = engine.run(
        [
            _plan("600001", "2026-07-01", industry="电力"),
            _plan("000001", "2026-07-02", industry="银行"),
        ],
        frames,
        benchmark=benchmark,
    )

    assert result["status"] == "ok"
    assert result["metrics"]["peak_positions"] == 2
    assert result["metrics"]["closed_trades"] == 2
    assert result["metrics"]["fees"] > 0
    assert result["metrics"]["benchmark_return_pct"] == 3.0
    assert result["metrics"]["excess_return_pct"] is not None
    assert result["audit"]["valid"] is True
    assert result["reconciliation"]["status"] == "ok"
    assert {row["strategy"] for row in result["attribution"]} == {"实验策略"}


def test_portfolio_backtest_reports_missing_trade_plans():
    result = PortfolioBacktestEngine(
        corporate_action_service=_StaticCorporateActionService(),
    ).run(
        [{"strategy": "实验策略", "plan_for_trade_date": "2026-07-01", "recommended": []}],
        {},
    )

    assert result["status"] == "insufficient_data"
    assert result["data_quality"]["errors"]


def test_portfolio_backtest_records_real_corporate_action_in_shared_account():
    frames = {
        "000001": _frame([
            {"date": "2026-06-10", "open": 10, "high": 10.1, "low": 9.9, "close": 10, "volume": 10_000_000},
            {"date": "2026-06-11", "open": 10, "high": 10.2, "low": 9.9, "close": 10.1, "volume": 10_000_000},
            {"date": "2026-06-12", "open": 9.8, "high": 10.0, "low": 9.7, "close": 9.9, "volume": 10_000_000},
        ]),
    }
    events = [{
        "action_id": "cash-000001-20260612",
        "symbol": "000001",
        "action_type": "cash_dividend",
        "effective_date": "2026-06-12",
        "record_date": "2026-06-11",
        "ex_date": "2026-06-12",
        "cash_per_share": 0.36,
        "source": "巨潮资讯历史分红/AKShare",
        "data_status": "verified",
    }]
    engine = PortfolioBacktestEngine(
        initial_cash=100_000,
        max_positions=1,
        position_pct=0.4,
        risk_limits=_risk_limits(),
        corporate_action_service=_StaticCorporateActionService(events),
    )

    result = engine.run([_plan("000001", "2026-06-11", target=20)], frames)

    assert result["status"] == "ok"
    assert len(result["corporate_actions"]) == 1
    assert result["corporate_actions"][0]["cash_effect"] > 0
    assert result["data_quality"]["corporate_actions"]["status"] == "ok"
    assert result["data_quality"]["corporate_actions"]["events_recorded"] == 1
