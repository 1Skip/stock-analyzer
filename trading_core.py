"""Shared order-state, audit, alert, and account-integrity helpers."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from math import isfinite
from typing import Any


ORDER_STATUS_PENDING = "pending"
ORDER_STATUS_PARTIALLY_FILLED = "partially_filled"
ORDER_STATUS_FILLED = "filled"
ORDER_STATUS_CANCELLED = "cancelled"
ORDER_STATUS_REJECTED = "rejected"
ORDER_STATUS_EXPIRED = "expired"

TERMINAL_ORDER_STATUSES = {
    ORDER_STATUS_FILLED,
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_REJECTED,
    ORDER_STATUS_EXPIRED,
}
ORDER_STATUS_TRANSITIONS = {
    None: {ORDER_STATUS_PENDING},
    ORDER_STATUS_PENDING: {
        ORDER_STATUS_PARTIALLY_FILLED,
        ORDER_STATUS_FILLED,
        ORDER_STATUS_CANCELLED,
        ORDER_STATUS_REJECTED,
        ORDER_STATUS_EXPIRED,
    },
    ORDER_STATUS_PARTIALLY_FILLED: {
        ORDER_STATUS_FILLED,
        ORDER_STATUS_CANCELLED,
        ORDER_STATUS_REJECTED,
    },
}


def transition_order(
    account: dict[str, Any],
    order: dict[str, Any],
    new_status: str,
    *,
    reason: str | None = None,
    occurred_at: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Move one order through the explicit state machine and audit the change."""
    current = order.get("status")
    if current == new_status:
        return
    allowed = ORDER_STATUS_TRANSITIONS.get(current, set())
    if new_status not in allowed:
        raise ValueError(f"非法订单状态迁移: {current!r} -> {new_status!r}")
    order["status"] = new_status
    order["status_updated_at"] = occurred_at or _now()
    if reason:
        order["reason"] = reason
    append_audit_event(
        account,
        "order_status_changed",
        {
            "order_id": order.get("order_id"),
            "symbol": order.get("symbol"),
            "side": order.get("side"),
            "from": current,
            "to": new_status,
            "reason": reason,
            **(details or {}),
        },
        occurred_at=occurred_at,
    )


def append_audit_event(
    account: dict[str, Any],
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    occurred_at: str | None = None,
) -> dict[str, Any]:
    """Append one immutable hash-chained audit event to the account."""
    events = account.setdefault("audit_events", [])
    previous_hash = str(events[-1].get("event_hash") or "") if events else ""
    body = {
        "sequence": len(events) + 1,
        "occurred_at": occurred_at or _now(),
        "event_type": str(event_type or "unknown"),
        "payload": _json_safe(payload or {}),
        "previous_hash": previous_hash,
    }
    event_hash = hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()
    event = {**body, "event_hash": event_hash}
    events.append(event)
    return event


def verify_audit_chain(events: Any) -> dict[str, Any]:
    """Verify sequence numbers, previous hashes, and event hashes."""
    if not isinstance(events, list):
        return {"valid": False, "events": 0, "error": "审计流水不是列表"}
    previous_hash = ""
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            return {"valid": False, "events": len(events), "error": f"第{index}条流水格式错误"}
        body = {
            "sequence": event.get("sequence"),
            "occurred_at": event.get("occurred_at"),
            "event_type": event.get("event_type"),
            "payload": event.get("payload") or {},
            "previous_hash": event.get("previous_hash") or "",
        }
        expected_hash = hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()
        if event.get("sequence") != index:
            return {"valid": False, "events": len(events), "error": f"第{index}条序号不连续"}
        if body["previous_hash"] != previous_hash:
            return {"valid": False, "events": len(events), "error": f"第{index}条前序哈希不匹配"}
        if event.get("event_hash") != expected_hash:
            return {"valid": False, "events": len(events), "error": f"第{index}条内容哈希不匹配"}
        previous_hash = expected_hash
    return {
        "valid": True,
        "events": len(events),
        "last_hash": previous_hash or None,
        "error": None,
    }


def append_alert(
    account: dict[str, Any],
    *,
    code: str,
    message: str,
    severity: str = "warning",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a deduplicated open alert and mirror it to the audit trail."""
    alerts = account.setdefault("alerts", [])
    for alert in reversed(alerts):
        if alert.get("code") == code and alert.get("status") == "open":
            alert["last_seen_at"] = _now()
            alert["occurrences"] = int(alert.get("occurrences") or 1) + 1
            if details:
                alert["details"] = _json_safe(details)
            return alert
    created_at = _now()
    alert = {
        "alert_id": hashlib.sha256(f"{code}|{created_at}|{len(alerts)}".encode("utf-8")).hexdigest()[:24],
        "code": str(code),
        "severity": str(severity),
        "message": str(message),
        "status": "open",
        "created_at": created_at,
        "last_seen_at": created_at,
        "occurrences": 1,
        "details": _json_safe(details or {}),
    }
    alerts.append(alert)
    append_audit_event(
        account,
        "alert_opened",
        {
            "alert_id": alert["alert_id"],
            "code": alert["code"],
            "severity": alert["severity"],
            "message": alert["message"],
        },
        occurred_at=created_at,
    )
    return alert


def acknowledge_alert(account: dict[str, Any], alert_id: str, *, note: str = "") -> bool:
    """Acknowledge an alert without deleting its history."""
    for alert in account.get("alerts") or []:
        if alert.get("alert_id") != alert_id or alert.get("status") != "open":
            continue
        alert["status"] = "acknowledged"
        alert["acknowledged_at"] = _now()
        alert["acknowledgement_note"] = str(note or "")
        append_audit_event(
            account,
            "alert_acknowledged",
            {"alert_id": alert_id, "note": str(note or "")},
        )
        return True
    return False


def build_account_integrity_report(
    account: dict[str, Any],
    *,
    cash_tolerance: float = 0.05,
) -> dict[str, Any]:
    """Recalculate cash and object identities for a formal end-of-day check."""
    errors: list[str] = []
    warnings: list[str] = []
    initial_cash = _number(account.get("initial_cash")) or 0.0
    recorded_cash = _number(account.get("cash"))
    cash_movements = 0.0
    fill_ids: set[str] = set()
    for fill in account.get("fills") or []:
        fill_id = str(fill.get("fill_id") or "")
        if not fill_id:
            errors.append("存在缺少 fill_id 的成交")
        elif fill_id in fill_ids:
            errors.append(f"成交编号重复: {fill_id}")
        fill_ids.add(fill_id)
        gross = _number(fill.get("gross_amount"))
        if gross is None:
            price = _number(fill.get("price")) or 0.0
            quantity = int(_number(fill.get("quantity")) or 0)
            gross = price * quantity
        fee = _number(fill.get("fee")) or 0.0
        if fill.get("side") == "BUY":
            cash_movements -= gross + fee
        elif fill.get("side") == "SELL":
            cash_movements += gross - fee
        else:
            errors.append(f"成交方向无效: {fill.get('side')}")
    for action in account.get("corporate_actions") or []:
        cash_movements += _number(action.get("cash_effect")) or 0.0
    expected_cash = initial_cash + cash_movements
    cash_difference = None if recorded_cash is None else recorded_cash - expected_cash
    if recorded_cash is None:
        errors.append("账户现金字段无效")
    elif abs(cash_difference or 0.0) > cash_tolerance:
        errors.append(f"现金账不平: 差额 {cash_difference:.4f}")
    if recorded_cash is not None and recorded_cash < -cash_tolerance:
        errors.append("账户现金为负")

    order_ids: set[str] = set()
    for order in account.get("orders") or []:
        order_id = str(order.get("order_id") or "")
        if not order_id:
            errors.append("存在缺少 order_id 的订单")
        elif order_id in order_ids:
            errors.append(f"订单编号重复: {order_id}")
        order_ids.add(order_id)
        status = order.get("status")
        if status not in {
            ORDER_STATUS_PENDING,
            ORDER_STATUS_PARTIALLY_FILLED,
            *TERMINAL_ORDER_STATUSES,
        }:
            errors.append(f"订单状态无效: {order_id}/{status}")

    for symbol, position in (account.get("positions") or {}).items():
        quantity = int(_number(position.get("quantity")) or 0)
        if quantity <= 0:
            errors.append(f"持仓数量无效: {symbol}")
        if quantity % 100:
            warnings.append(f"持仓不是100股整数手: {symbol}/{quantity}")

    audit = verify_audit_chain(account.get("audit_events") or [])
    if not audit["valid"]:
        errors.append(f"审计链无效: {audit.get('error')}")
    return {
        "status": "ok" if not errors else "failed",
        "checked_at": _now(),
        "recorded_cash": round(recorded_cash, 4) if recorded_cash is not None else None,
        "expected_cash": round(expected_cash, 4),
        "cash_difference": round(cash_difference, 4) if cash_difference is not None else None,
        "orders": len(account.get("orders") or []),
        "fills": len(account.get("fills") or []),
        "positions": len(account.get("positions") or {}),
        "closed_trades": len(account.get("closed_trades") or []),
        "audit": audit,
        "errors": errors,
        "warnings": warnings,
    }


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
