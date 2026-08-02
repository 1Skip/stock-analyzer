import broker_execution
from broker_execution import (
    BrokerOrderRequest,
    DisabledBrokerAdapter,
    QmtBrokerAdapter,
    normalize_qmt_order_status,
)


def test_default_paper_adapter_blocks_real_orders():
    adapter = DisabledBrokerAdapter()
    request = BrokerOrderRequest(
        client_order_id="local-1",
        symbol="600001",
        side="BUY",
        quantity=100,
        limit_price=10,
    )

    assert adapter.readiness()["live_order_enabled"] is False
    assert adapter.submit_order(request)["status"] == "blocked"


def test_qmt_live_requires_all_three_gates(monkeypatch):
    monkeypatch.setattr(broker_execution.os, "name", "nt")
    monkeypatch.setattr(
        broker_execution.importlib.util,
        "find_spec",
        lambda name: object() if name == "xtquant" else None,
    )
    adapter = QmtBrokerAdapter(
        mode="qmt_live",
        userdata_path="C:/qmt/userdata",
        account_id="123456",
        live_enabled=True,
        live_confirmation="WRONG",
    )

    readiness = adapter.readiness()

    assert readiness["ready"] is True
    assert readiness["live_order_enabled"] is False
    assert adapter.submit_order(
        BrokerOrderRequest("o1", "600001", "BUY", 100, 10)
    )["status"] == "blocked"


def test_qmt_read_only_never_enables_orders(monkeypatch):
    monkeypatch.setattr(broker_execution.os, "name", "nt")
    monkeypatch.setattr(broker_execution.importlib.util, "find_spec", lambda name: object())
    adapter = QmtBrokerAdapter(
        mode="qmt_read_only",
        userdata_path="C:/qmt/userdata",
        account_id="123456",
        live_enabled=True,
        live_confirmation=broker_execution.LIVE_CONFIRMATION_PHRASE,
    )

    assert adapter.readiness()["ready"] is True
    assert adapter.readiness()["read_only"] is True
    assert adapter.readiness()["live_order_enabled"] is False


def test_qmt_order_status_maps_to_shared_state_machine():
    assert normalize_qmt_order_status(50) == "pending"
    assert normalize_qmt_order_status(55) == "partially_filled"
    assert normalize_qmt_order_status(56) == "filled"
    assert normalize_qmt_order_status(54) == "cancelled"
    assert normalize_qmt_order_status(57) == "rejected"
    assert normalize_qmt_order_status("unexpected") == "unknown"
