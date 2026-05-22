def test_t1_plan_report_includes_generated_strategy_stocks():
    from notification import build_t1_plan_report

    title, body = build_t1_plan_report({
        "??????": {
            "generated_at": "2026-05-19T15:45:00",
            "plan_for_trade_date": "2026-05-20",
            "sector": "??",
            "recommended": [{
                "symbol": "002001",
                "name": "??T1",
                "latest_price": 10.0,
                "change_pct": 1.2,
                "strategy": "??????",
                "score": 88,
                "rating": "?????",
                "indicators": {},
                "trade_plan": {
                    "buy_zone": "9.80-10.10",
                    "stop_loss": 9.5,
                    "take_profit_1": 11.2,
                    "position": "1-2?",
                    "add_condition": "??MA5",
                    "invalid_conditions": ["?????"],
                },
            }],
        }
    })

    assert "T+1" in title
    assert "??????" in body
    assert "002001" in body
    assert "???" in body
    assert "9.80-10.10" in body
    assert "??????" in body


def test_t1_plan_preheat_builds_local_summary(monkeypatch):
    import scheduler

    seen = {}
    monkeypatch.setattr(
        scheduler,
        "build_t1_plan_report",
        lambda plans: seen.setdefault("plans", plans) or ("T+1 ????", "??????\n002001"),
    )

    scheduler._push_t1_plan_preheat_results({
        "??????": {"recommended": [{"symbol": "002001"}]},
        "?????": None,
    })

    assert "??????" in seen["plans"]
