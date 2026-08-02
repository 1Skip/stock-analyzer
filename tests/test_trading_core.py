from trading_core import (
    append_audit_event,
    build_account_integrity_report,
    transition_order,
    verify_audit_chain,
)


def test_audit_chain_detects_mutation():
    account = {"audit_events": []}
    append_audit_event(account, "account_created", {"cash": 100_000})
    append_audit_event(account, "order_created", {"order_id": "o1"})

    assert verify_audit_chain(account["audit_events"])["valid"] is True

    account["audit_events"][0]["payload"]["cash"] = 1

    result = verify_audit_chain(account["audit_events"])
    assert result["valid"] is False
    assert "哈希" in result["error"]


def test_order_state_machine_rejects_terminal_transition():
    account = {"audit_events": []}
    order = {"order_id": "o1", "symbol": "600001", "side": "BUY", "status": "pending"}

    transition_order(account, order, "filled")

    assert order["status"] == "filled"
    try:
        transition_order(account, order, "cancelled")
    except ValueError as exc:
        assert "非法订单状态迁移" in str(exc)
    else:
        raise AssertionError("terminal order transition should fail")


def test_integrity_report_recalculates_cash_from_fills():
    account = {
        "initial_cash": 100_000,
        "cash": 89_994,
        "orders": [{"order_id": "o1", "status": "filled"}],
        "fills": [
            {
                "fill_id": "f1",
                "side": "BUY",
                "gross_amount": 10_000,
                "fee": 6,
            }
        ],
        "positions": {"600001": {"quantity": 100}},
        "closed_trades": [],
        "corporate_actions": [],
        "audit_events": [],
    }
    append_audit_event(account, "account_created", {"cash": 100_000})

    report = build_account_integrity_report(account)

    assert report["status"] == "ok"
    assert report["cash_difference"] == 0
