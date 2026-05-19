from unittest.mock import MagicMock


def test_t1_plan_report_includes_generated_strategy_stocks():
    from notification import build_t1_plan_report

    title, body = build_t1_plan_report({
        "多因子稳健型": {
            "generated_at": "2026-05-19T15:45:00",
            "plan_for_trade_date": "2026-05-20",
            "sector": "全部",
            "recommended": [{
                "symbol": "002001",
                "name": "测试T1",
                "latest_price": 10.0,
                "change_pct": 1.2,
                "strategy": "多因子稳健型",
                "score": 88,
                "rating": "多因子共振",
                "indicators": {},
                "trade_plan": {
                    "buy_zone": "9.80-10.10",
                    "stop_loss": 9.5,
                    "take_profit_1": 11.2,
                    "position": "1-2成",
                    "add_condition": "站稳MA5",
                    "invalid_conditions": ["跌破止损线"],
                },
            }],
        }
    })

    assert "T+1" in title
    assert "多因子稳健型" in body
    assert "002001" in body
    assert "买卖点" in body
    assert "9.80-10.10" in body
    assert "交易计划卡片" in body


def test_t1_plan_preheat_pushes_generated_plans(monkeypatch):
    import scheduler

    sent = {}

    monkeypatch.setattr(scheduler, "T1_PLAN_PUSH_ENABLED", True)
    monkeypatch.setattr(scheduler, "NOTIFY_ENABLED", True)
    monkeypatch.setattr(
        scheduler,
        "build_t1_plan_report",
        lambda plans: ("T+1 推荐计划", "多因子稳健型\n002001"),
    )
    monkeypatch.setattr(scheduler, "send_push", lambda title, body: sent.setdefault("payload", (title, body)) or {"feishu": True})

    scheduler._push_t1_plan_preheat_results({
        "多因子稳健型": {
            "recommended": [{"symbol": "002001"}],
            "generation_metrics": {"elapsed_seconds": 1},
        },
        "激进突破型": None,
    })

    assert sent["payload"] == ("T+1 推荐计划", "多因子稳健型\n002001")


def test_t1_plan_preheat_push_respects_switch(monkeypatch):
    import scheduler

    send_push = MagicMock()
    monkeypatch.setattr(scheduler, "T1_PLAN_PUSH_ENABLED", False)
    monkeypatch.setattr(scheduler, "NOTIFY_ENABLED", True)
    monkeypatch.setattr(scheduler, "send_push", send_push)

    scheduler._push_t1_plan_preheat_results({"多因子稳健型": {"recommended": []}})

    send_push.assert_not_called()
