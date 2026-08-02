import json

from experimental_strategy import (
    EXPERIMENTAL_RULE_ID,
    EXPERIMENTAL_STRATEGY_NAME,
    EXPERIMENTAL_STRATEGY_VERSION,
)
from paper_trading import LOT_SIZE, PaperTradingService


def _plan(*, symbol="600001", trade_date="2026-07-01", stop_loss=9.5, take_profit=10.5):
    return {
        "strategy": EXPERIMENTAL_STRATEGY_NAME,
        "strategy_version": EXPERIMENTAL_STRATEGY_VERSION,
        "strategy_rule_id": EXPERIMENTAL_RULE_ID,
        "sector": "全部",
        "plan_for_trade_date": trade_date,
        "recommended": [
            {
                "symbol": symbol,
                "name": "测试股",
                "trade_plan": {
                    "buy_zone_low": 9.8,
                    "buy_zone_high": 10.2,
                    "stop_loss": stop_loss,
                    "take_profit_1": take_profit,
                    "max_holding_days": 5,
                },
            }
        ],
    }


def _write_kline(tmp_path, rows, *, symbol="600001"):
    directory = tmp_path / "strategy_kline_daily"
    directory.mkdir(parents=True, exist_ok=True)
    columns = ["open", "high", "low", "close", "volume"]
    payload = {
        "columns": columns,
        "index": [row["date"] for row in rows],
        "data": [[row[column] for column in columns] for row in rows],
    }
    path = directory / f"CN_{symbol}_1y_1d_qfq.json"
    path.write_text(json.dumps(payload), encoding="utf-8")


def _row(date, open_price, high, low, close, volume=10_000_000):
    return {
        "date": date,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def test_candidate_plan_is_deduplicated_and_buys_from_real_daily_k(tmp_path):
    _write_kline(
        tmp_path,
        [
            _row("2026-06-30", 9.9, 10.1, 9.8, 10.0),
            _row("2026-07-01", 10.0, 10.3, 9.9, 10.1),
        ],
    )
    service = PaperTradingService(cache_dir=tmp_path)

    synced = service.sync_candidate_plan(_plan())
    duplicate = service.sync_candidate_plan(_plan())
    result = service.reconcile(as_of_date="2026-07-01")

    assert synced["created_orders"] == 1
    assert duplicate["status"] == "duplicate"
    assert result["buy_orders"]["filled"] == 1
    assert result["position_exits"]["filled"] == 0
    assert result["summary"]["open_positions"] == 1
    assert result["summary"]["positions"][0]["available_quantity"] == 0
    fill = result["summary"]["recent_fills"][0]
    assert fill["quantity"] % LOT_SIZE == 0
    assert fill["price_source"].startswith("策略K线本地真实缓存/")
    assert "真实日K" in fill["price_evidence"]
    assert "非逐笔成交回放" in fill["execution_model"]


def test_t_plus_one_blocks_same_day_exit_and_next_day_can_sell(tmp_path):
    _write_kline(
        tmp_path,
        [
            _row("2026-06-30", 9.9, 10.1, 9.8, 10.0),
            _row("2026-07-01", 10.0, 10.3, 9.9, 10.1),
            _row("2026-07-02", 9.7, 9.9, 9.4, 9.6),
        ],
    )
    service = PaperTradingService(cache_dir=tmp_path)
    service.sync_candidate_plan(_plan())

    same_day = service.reconcile(as_of_date="2026-07-01")
    next_day = service.reconcile(as_of_date="2026-07-02")

    assert same_day["summary"]["open_positions"] == 1
    assert same_day["summary"]["closed_trades"] == 0
    assert next_day["position_exits"]["filled"] == 1
    assert next_day["summary"]["open_positions"] == 0
    trade = next_day["summary"]["recent_closed_trades"][0]
    assert trade["sell_date"] == "2026-07-02"
    assert trade["strategy_rule_id"] == EXPERIMENTAL_RULE_ID
    assert next_day["summary"]["strategy_performance"][0][
        "strategy_rule_id"
    ] == EXPERIMENTAL_RULE_ID


def test_one_price_limit_up_cannot_fill_buy_order(tmp_path):
    _write_kline(
        tmp_path,
        [
            _row("2026-06-30", 9.9, 10.1, 9.8, 10.0),
            _row("2026-07-01", 11.0, 11.0, 11.0, 11.0),
        ],
    )
    service = PaperTradingService(cache_dir=tmp_path)
    service.sync_candidate_plan(_plan())

    result = service.reconcile(as_of_date="2026-07-01")

    assert result["buy_orders"]["expired"] == 1
    assert result["summary"]["fills"] == 0
    assert result["summary"]["open_positions"] == 0


def test_missing_real_daily_k_keeps_order_pending(tmp_path):
    service = PaperTradingService(cache_dir=tmp_path)
    service.sync_candidate_plan(_plan())

    result = service.reconcile(as_of_date="2026-07-01")

    assert result["buy_orders"]["pending"] == 1
    assert result["summary"]["pending_orders"] == 1
    assert result["summary"]["fills"] == 0


def test_fees_are_deducted_from_closed_trade_profit(tmp_path):
    _write_kline(
        tmp_path,
        [
            _row("2026-06-30", 9.9, 10.1, 9.8, 10.0),
            _row("2026-07-01", 10.0, 10.3, 9.9, 10.1),
            _row("2026-07-02", 10.2, 10.6, 10.1, 10.5),
        ],
    )
    service = PaperTradingService(cache_dir=tmp_path)
    service.sync_candidate_plan(_plan())
    service.reconcile(as_of_date="2026-07-01")

    result = service.reconcile(as_of_date="2026-07-02")
    trade = result["summary"]["recent_closed_trades"][0]
    gross_profit = (trade["sell_price"] - trade["buy_price"]) * trade["quantity"]

    assert trade["pnl"] > 0
    assert trade["pnl"] < gross_profit
    assert trade["buy_fee"] > 0
    assert trade["sell_fee"] > 0


def test_limit_down_exit_stays_blocked_then_sells_on_first_tradable_day(tmp_path):
    _write_kline(
        tmp_path,
        [
            _row("2026-06-30", 9.9, 10.1, 9.8, 10.0),
            _row("2026-07-01", 10.0, 10.3, 9.9, 10.1),
            _row("2026-07-02", 9.09, 9.09, 9.09, 9.09),
            _row("2026-07-03", 8.8, 9.1, 8.7, 9.0),
        ],
    )
    service = PaperTradingService(cache_dir=tmp_path)
    service.sync_candidate_plan(_plan(stop_loss=9.5))
    service.reconcile(as_of_date="2026-07-01")

    blocked = service.reconcile(as_of_date="2026-07-02")
    released = service.reconcile(as_of_date="2026-07-03")

    assert blocked["position_exits"]["blocked_limit_down"] == 1
    assert blocked["summary"]["open_positions"] == 1
    assert released["position_exits"]["filled"] == 1
    trade = released["summary"]["recent_closed_trades"][0]
    assert trade["sell_price"] == 8.8
    assert "首个可交易日开盘退出" in trade["exit_reason"]


def test_losing_paper_rule_moves_to_cash_after_30_settled_trades(tmp_path):
    _write_kline(
        tmp_path,
        [
            _row("2026-07-01", 9.9, 10.1, 9.8, 10.0),
            _row("2026-07-02", 10.0, 10.3, 9.9, 10.1),
        ],
    )
    service = PaperTradingService(cache_dir=tmp_path)
    service.sync_candidate_plan(_plan(trade_date="2026-07-02"))
    account = service.get_account()
    account["closed_trades"] = [
        {
            "trade_id": f"t{index}",
            "strategy": EXPERIMENTAL_STRATEGY_NAME,
            "strategy_version": EXPERIMENTAL_STRATEGY_VERSION,
            "strategy_rule_id": EXPERIMENTAL_RULE_ID,
            "pnl": -10,
            "return_pct": -0.1,
            "is_win": False,
        }
        for index in range(30)
    ]
    account["realized_pnl"] = -300
    service._save(account)

    result = service.reconcile(as_of_date="2026-07-02")

    assert result["strategy_rotation"]["action"] == "cash"
    assert result["buy_orders"]["filled"] == 0
    assert result["summary"]["strategy_control"]["status"] == "cash"
    assert result["summary"]["strategy_control"]["active_rule_id"] is None
    assert result["summary"]["pending_orders"] == 0


def test_v2_pending_orders_are_cancelled_when_control_upgrades_to_v3(tmp_path):
    service = PaperTradingService(cache_dir=tmp_path)
    account = service.get_account()
    account["strategy_control"].update({
        "active_rule_id": "pullback_recovery_regime",
        "active_strategy_version": "market_regime_pullback_v2",
    })
    account["orders"] = [
        {
            "order_id": "legacy-order",
            "side": "BUY",
            "status": "pending",
            "strategy_rule_id": "pullback_recovery_regime",
            "strategy_version": "market_regime_pullback_v2",
        }
    ]
    service._save(account)

    control = service.get_strategy_control()
    migrated = service.get_account()

    assert control["active_rule_id"] == EXPERIMENTAL_RULE_ID
    assert control["active_strategy_version"] == EXPERIMENTAL_STRATEGY_VERSION
    assert migrated["orders"][0]["status"] == "cancelled"
