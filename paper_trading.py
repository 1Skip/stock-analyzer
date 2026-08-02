"""Unified paper account, order, fill, position, and cash accounting."""
from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
from math import floor, isfinite
from pathlib import Path
from typing import Any

import pandas as pd

from config import (
    PAPER_TRADING_INITIAL_CASH,
    PAPER_TRADING_MAX_POSITIONS,
    PAPER_TRADING_POSITION_PCT,
    PAPER_TRADING_STRATEGIES,
    PORTFOLIO_MAX_DAILY_LOSS_PCT,
    PORTFOLIO_MAX_DATA_AGE_DAYS,
    PORTFOLIO_MAX_DRAWDOWN_PCT,
    PORTFOLIO_MAX_INDUSTRY_EXPOSURE_PCT,
    PORTFOLIO_MAX_ORDER_PARTICIPATION_PCT,
    RUNTIME_CACHE_DIR,
)
from data.cache import JsonFileCache
from data.services.corporate_action_service import CorporateActionService
from experimental_strategy import (
    EXPERIMENTAL_RULE_ID,
    EXPERIMENTAL_STRATEGY_NAME,
    EXPERIMENTAL_STRATEGY_VERSION,
)
from portfolio_risk import PortfolioRiskEngine, PortfolioRiskLimits
from quality_monitor import build_plan_history_identity
from strategy_rotation import build_rotation_decision, load_strategy_research
from trading_core import (
    acknowledge_alert as acknowledge_account_alert,
    append_alert,
    append_audit_event,
    build_account_integrity_report,
    transition_order,
    verify_audit_chain,
)


PAPER_ACCOUNT_VERSION = "paper_account_v3"
LEGACY_PAPER_ACCOUNT_VERSIONS = {"paper_account_v1", "paper_account_v2"}
DEFAULT_ACCOUNT_ID = "experimental_candidate"
PAPER_ACCOUNT_TTL_SECONDS = 86400 * 365 * 10
COMMISSION_RATE = 0.0003
MIN_COMMISSION = 5.0
STAMP_DUTY_RATE = 0.0005
TRANSFER_FEE_RATE = 0.00001
LOT_SIZE = 100
LEGACY_EXPERIMENTAL_RULE_VERSIONS = {
    ("market_regime_pullback_v2", "pullback_recovery_regime"),
}


class PaperTradingService:
    """Persist and reconcile a candidate-only A-share paper account."""

    def __init__(
        self,
        *,
        cache: JsonFileCache | None = None,
        cache_dir: str | Path | None = None,
        account_id: str = DEFAULT_ACCOUNT_ID,
        initial_cash: float = PAPER_TRADING_INITIAL_CASH,
        max_positions: int = PAPER_TRADING_MAX_POSITIONS,
        position_pct: float = PAPER_TRADING_POSITION_PCT,
        allowed_strategies: list[str] | tuple[str, ...] | set[str] | None = None,
        risk_engine: PortfolioRiskEngine | None = None,
        strategy_rotation_enabled: bool | None = None,
        corporate_action_service: CorporateActionService | None = None,
    ):
        self.cache = cache or JsonFileCache(
            "paper_trading_accounts",
            PAPER_ACCOUNT_TTL_SECONDS,
            cache_dir=cache_dir,
        )
        self.cache_dir = Path(cache_dir or RUNTIME_CACHE_DIR)
        self.account_id = str(account_id or DEFAULT_ACCOUNT_ID)
        self.initial_cash = max(0.0, float(initial_cash))
        self.max_positions = max(1, int(max_positions))
        self.position_pct = max(0.01, min(1.0, float(position_pct)))
        configured_strategies = PAPER_TRADING_STRATEGIES if allowed_strategies is None else allowed_strategies
        self.allowed_strategies = {
            str(strategy).strip() for strategy in configured_strategies if str(strategy).strip()
        }
        self.strategy_rotation_enabled = (
            self.account_id == DEFAULT_ACCOUNT_ID
            if strategy_rotation_enabled is None
            else bool(strategy_rotation_enabled)
        )
        self.corporate_action_service = corporate_action_service or CorporateActionService(
            cache_dir=self.cache_dir,
        )
        self.risk_engine = risk_engine or PortfolioRiskEngine(
            PortfolioRiskLimits(
                max_drawdown_pct=PORTFOLIO_MAX_DRAWDOWN_PCT,
                max_daily_loss_pct=PORTFOLIO_MAX_DAILY_LOSS_PCT,
                max_industry_exposure_pct=PORTFOLIO_MAX_INDUSTRY_EXPOSURE_PCT,
                max_order_participation_pct=PORTFOLIO_MAX_ORDER_PARTICIPATION_PCT,
                max_data_age_days=PORTFOLIO_MAX_DATA_AGE_DAYS,
            )
        )

    def get_account(self) -> dict[str, Any]:
        account = self.cache.get(self.account_id)
        if isinstance(account, dict) and account.get("version") in LEGACY_PAPER_ACCOUNT_VERSIONS:
            account = self._migrate_account(account)
            self._save(account)
        if not isinstance(account, dict) or account.get("version") != PAPER_ACCOUNT_VERSION:
            account = self._new_account()
            self._save(account)
        return account

    def sync_candidate_plan(self, plan: dict[str, Any] | None) -> dict[str, Any]:
        """Backward-compatible alias for the unified plan intake."""
        return self.sync_plan(plan)

    def sync_plan(self, plan: dict[str, Any] | None) -> dict[str, Any]:
        """Create deduplicated pending buy orders from one real strategy plan."""
        if not isinstance(plan, dict):
            return {"status": "invalid_plan", "created_orders": 0, "message": "缺少有效推荐计划"}
        strategy = str(plan.get("strategy") or "").strip()
        if strategy not in self.allowed_strategies:
            return {
                "status": "ignored",
                "created_orders": 0,
                "message": f"策略未进入统一账户白名单: {strategy or '--'}",
            }
        account = self.get_account()
        strategy_rule_id = _plan_rule_id(plan)
        strategy_version = str(plan.get("strategy_version") or "").strip()
        if (
            self.strategy_rotation_enabled
            and strategy == EXPERIMENTAL_STRATEGY_NAME
        ):
            strategy_rule_id = strategy_rule_id or EXPERIMENTAL_RULE_ID
            strategy_version = strategy_version or EXPERIMENTAL_STRATEGY_VERSION
            control = self._ensure_strategy_control(account)
            if control.get("status") == "cash":
                return {
                    "status": "strategy_paused",
                    "created_orders": 0,
                    "message": control.get("reason") or "实验策略当前保持现金",
                }
            if (
                strategy_rule_id != control.get("active_rule_id")
                or strategy_version != control.get("active_strategy_version")
            ):
                return {
                    "status": "stale_strategy_rule",
                    "created_orders": 0,
                    "message": "计划规则版本不是模拟账户当前活动版本，已拒绝下单",
                    "active_rule_id": control.get("active_rule_id"),
                    "active_strategy_version": control.get("active_strategy_version"),
                }
        identity = build_plan_history_identity(plan)
        if not identity:
            return {"status": "invalid_plan", "created_orders": 0, "message": "计划缺少稳定标识"}
        if strategy_version or strategy_rule_id:
            identity = (
                f"{identity}|{strategy_version or '--'}|"
                f"{strategy_rule_id or '--'}"
            )
        synced = account.setdefault("synced_plan_ids", [])
        if identity in synced:
            return {"status": "duplicate", "created_orders": 0, "plan_identity": identity}

        planned_date = str(
            plan.get("plan_for_trade_date")
            or plan.get("generated_trade_date")
            or plan.get("generated_at")
            or ""
        )[:10]
        active_symbols = set(account.get("positions") or {})
        active_symbols.update(
            str(order.get("symbol") or "")
            for order in account.get("orders") or []
            if order.get("status") == "pending"
        )
        available_slots = max(
            0,
            self.max_positions
            - len(account.get("positions") or {})
            - sum(1 for order in account.get("orders") or [] if order.get("status") == "pending"),
        )
        created = []
        for stock in plan.get("recommended") or []:
            if available_slots <= 0:
                break
            symbol = str((stock or {}).get("symbol") or "").strip()
            trade_plan = stock.get("trade_plan") if isinstance(stock.get("trade_plan"), dict) else {}
            buy_low = _number(trade_plan.get("buy_zone_low"))
            buy_high = _number(trade_plan.get("buy_zone_high"))
            if (
                not symbol
                or symbol in active_symbols
                or buy_low is None
                or buy_high is None
                or buy_low <= 0
                or buy_high <= 0
            ):
                continue
            if buy_low > buy_high:
                buy_low, buy_high = buy_high, buy_low
            target_value = self.initial_cash * self.position_pct
            quantity = floor(target_value / buy_high / LOT_SIZE) * LOT_SIZE
            if quantity < LOT_SIZE:
                continue
            order_id = _stable_id(self.account_id, identity, symbol, "BUY")
            order = {
                "order_id": order_id,
                "plan_identity": identity,
                "history_key": plan.get("history_key"),
                "strategy": plan.get("strategy"),
                "strategy_version": strategy_version or plan.get("strategy_version"),
                "strategy_rule_id": strategy_rule_id,
                "symbol": symbol,
                "name": stock.get("name") or symbol,
                "industry": (
                    stock.get("industry")
                    or (stock.get("profile") or {}).get("industry")
                    or "未知行业"
                ),
                "side": "BUY",
                "order_type": "LIMIT_RANGE",
                "status": "pending",
                "quantity": quantity,
                "filled_quantity": 0,
                "buy_zone_low": round(buy_low, 3),
                "buy_zone_high": round(buy_high, 3),
                "stop_loss": _round_price(trade_plan.get("stop_loss")),
                "take_profit_1": _round_price(trade_plan.get("take_profit_1")),
                "max_holding_days": max(1, int(_number(trade_plan.get("max_holding_days")) or 5)),
                "scheduled_date": planned_date,
                "created_at": _now(),
                "price_source_required": "后续真实A股日K",
            }
            account.setdefault("orders", []).append(order)
            append_audit_event(
                account,
                "order_created",
                {
                    "order_id": order_id,
                    "plan_identity": identity,
                    "strategy": strategy,
                    "strategy_version": order.get("strategy_version"),
                    "strategy_rule_id": order.get("strategy_rule_id"),
                    "symbol": symbol,
                    "side": "BUY",
                    "quantity": quantity,
                    "scheduled_date": planned_date,
                    "buy_zone_low": order["buy_zone_low"],
                    "buy_zone_high": order["buy_zone_high"],
                },
            )
            created.append(order_id)
            active_symbols.add(symbol)
            available_slots -= 1

        synced.append(identity)
        account.setdefault("plan_syncs", []).append({
            "plan_identity": identity,
            "strategy": plan.get("strategy"),
            "strategy_version": strategy_version or plan.get("strategy_version"),
            "strategy_rule_id": strategy_rule_id,
            "planned_date": planned_date,
            "recommended": len(plan.get("recommended") or []),
            "created_orders": len(created),
            "synced_at": _now(),
        })
        account["synced_plan_ids"] = synced[-1000:]
        account["plan_syncs"] = account["plan_syncs"][-1000:]
        append_audit_event(
            account,
            "plan_synced",
            {
                "plan_identity": identity,
                "strategy": strategy,
                "strategy_version": strategy_version,
                "strategy_rule_id": strategy_rule_id,
                "planned_date": planned_date,
                "recommended": len(plan.get("recommended") or []),
                "created_orders": len(created),
            },
        )
        self._save(account)
        return {
            "status": "ok",
            "plan_identity": identity,
            "created_orders": len(created),
            "order_ids": created,
        }

    def reconcile(self, *, as_of_date: Any = None) -> dict[str, Any]:
        """Apply real daily K evidence to pending orders and open positions."""
        as_of = _date_text(as_of_date) or date.today().isoformat()
        account = self.get_account()
        append_audit_event(account, "reconciliation_started", {"as_of_date": as_of})
        corporate_actions = self._sync_corporate_actions(account, as_of)
        account["last_corporate_action_sync"] = corporate_actions
        pre_trade_equity = self._estimate_equity(account, as_of)
        pre_trade_risk = self.risk_engine.update_account_state(
            account,
            equity=pre_trade_equity,
            as_of_date=as_of,
        )
        if pre_trade_risk.get("automatic_breaches"):
            append_alert(
                account,
                code="PORTFOLIO_RISK_BREACH",
                severity="critical",
                message="；".join(pre_trade_risk["automatic_breaches"]),
                details={"as_of_date": as_of, "risk": pre_trade_risk},
            )
        pre_entry_rotation = self._apply_strategy_rotation(account)
        buy_result = self._process_pending_buys(account, as_of)
        sell_result = self._process_position_exits(account, as_of)
        post_exit_rotation = self._apply_strategy_rotation(account)
        strategy_rotation = (
            pre_entry_rotation
            if pre_entry_rotation.get("action") in {"switch", "cash"}
            and pre_entry_rotation.get("failed_rule_versions")
            else post_exit_rotation
        )
        account["last_reconciled_date"] = as_of
        account["last_reconciled_at"] = _now()
        summary = self._summarize(account, as_of)
        self._record_equity_snapshot(account, summary)
        risk = self.risk_engine.update_account_state(
            account,
            equity=float(summary.get("equity") or 0),
            as_of_date=as_of,
        )
        integrity = build_account_integrity_report(account)
        reconciliation = {
            **integrity,
            "as_of_date": as_of,
            "equity": summary.get("equity"),
            "market_value": summary.get("market_value"),
            "risk": self.risk_engine.summary(account),
            "corporate_actions": corporate_actions,
        }
        account.setdefault("reconciliations", []).append(reconciliation)
        account["reconciliations"] = account["reconciliations"][-1000:]
        if integrity["status"] != "ok":
            append_alert(
                account,
                code="ACCOUNT_RECONCILIATION_FAILED",
                severity="critical",
                message="统一交易账户日终对账失败",
                details={"as_of_date": as_of, "errors": integrity["errors"]},
            )
        append_audit_event(
            account,
            "reconciliation_finished",
            {
                "as_of_date": as_of,
                "equity": summary.get("equity"),
                "cash": summary.get("cash"),
                "market_value": summary.get("market_value"),
                "integrity_status": integrity["status"],
                "risk_breaches": risk.get("automatic_breaches") or [],
            },
        )
        self._save(account)
        summary = self._summarize(account, as_of)
        return {
            "status": "ok" if integrity["status"] == "ok" else "reconciliation_failed",
            "as_of_date": as_of,
            "buy_orders": buy_result,
            "position_exits": sell_result,
            "corporate_actions": corporate_actions,
            "strategy_rotation": strategy_rotation,
            "summary": summary,
            "risk": self.risk_engine.summary(account),
            "reconciliation": reconciliation,
        }

    def get_summary(self, *, as_of_date: Any = None) -> dict[str, Any]:
        as_of = _date_text(as_of_date) or date.today().isoformat()
        return self._summarize(self.get_account(), as_of)

    def get_strategy_control(self) -> dict[str, Any]:
        account = self.get_account()
        control = self._ensure_strategy_control(account)
        self._save(account)
        return dict(control)

    def set_emergency_halt(self, *, enabled: bool, reason: str) -> dict[str, Any]:
        """Block new entries immediately while preserving an auditable manual action."""
        account = self.get_account()
        risk = self.risk_engine.set_manual_halt(account, enabled=enabled, reason=reason)
        cancelled = 0
        if enabled:
            cancelled = self._cancel_pending_orders(account, reason=f"紧急停机: {reason}")
            append_alert(
                account,
                code="MANUAL_EMERGENCY_HALT",
                severity="critical",
                message=f"人工紧急停机已开启: {reason}",
            )
        append_audit_event(
            account,
            "manual_halt_changed",
            {"enabled": bool(enabled), "reason": str(reason or ""), "cancelled_orders": cancelled},
        )
        self._save(account)
        return {
            "status": "ok",
            "enabled": bool(enabled),
            "cancelled_orders": cancelled,
            "risk": self.risk_engine.summary(account),
        }

    def cancel_pending_orders(self, *, reason: str = "人工撤销") -> dict[str, Any]:
        account = self.get_account()
        cancelled = self._cancel_pending_orders(account, reason=reason)
        self._save(account)
        return {"status": "ok", "cancelled_orders": cancelled}

    def acknowledge_alert(self, alert_id: str, *, note: str = "") -> dict[str, Any]:
        account = self.get_account()
        acknowledged = acknowledge_account_alert(account, alert_id, note=note)
        if acknowledged:
            self._save(account)
        return {"status": "ok" if acknowledged else "not_found", "alert_id": alert_id}

    def record_alert(
        self,
        *,
        code: str,
        message: str,
        severity: str = "warning",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        account = self.get_account()
        alert = append_alert(
            account,
            code=code,
            message=message,
            severity=severity,
            details=details,
        )
        self._save(account)
        return alert

    def apply_corporate_action(self, action: dict[str, Any]) -> dict[str, Any]:
        """Apply one externally sourced company action and persist it idempotently."""
        account = self.get_account()
        result = self._apply_corporate_action_to_account(account, action)
        if result.get("status") in {"ok", "not_subscribed"}:
            self._save(account)
        return result

    def _apply_corporate_action_to_account(
        self,
        account: dict[str, Any],
        action: dict[str, Any],
    ) -> dict[str, Any]:
        action_id = str(action.get("action_id") or "").strip()
        symbol = str(action.get("symbol") or "").strip()
        action_type = str(action.get("action_type") or "").strip()
        source = str(action.get("source") or "").strip()
        if not action_id or not symbol or not source:
            return {"status": "invalid", "message": "公司行为必须包含 action_id、symbol 和真实来源"}
        if any(row.get("action_id") == action_id for row in account.get("corporate_actions") or []):
            return {"status": "duplicate", "action_id": action_id}
        position = (account.get("positions") or {}).get(symbol)
        if not isinstance(position, dict):
            return {"status": "ignored", "message": "除权日账户没有对应持仓"}
        record_date = _date_text(action.get("record_date"))
        buy_date = _date_text(position.get("buy_date"))
        if record_date and buy_date and buy_date > record_date:
            return {"status": "ignored", "message": "股权登记日账户尚未持仓"}
        quantity = int(position.get("quantity") or 0)
        record = {
            "action_id": action_id,
            "symbol": symbol,
            "action_type": action_type,
            "effective_date": _date_text(action.get("effective_date")),
            "announcement_date": _date_text(action.get("announcement_date")),
            "record_date": record_date,
            "ex_date": _date_text(action.get("ex_date")),
            "source": source,
            "data_status": action.get("data_status") or "externally_provided",
            "description": action.get("description"),
            "cash_effect": 0.0,
            "quantity_before": quantity,
            "quantity_after": quantity,
            "applied_at": _now(),
            "status": "applied",
        }
        if action_type == "cash_dividend":
            cash_per_share = _number(action.get("cash_per_share"))
            if cash_per_share is None or cash_per_share <= 0:
                return {"status": "invalid", "message": "现金分红金额无效"}
            cash_effect = quantity * cash_per_share
            account["cash"] = round(float(account.get("cash") or 0) + cash_effect, 4)
            record["cash_per_share"] = cash_per_share
            record["cash_per_10_shares"] = _number(action.get("cash_per_10_shares"))
            record["payment_date"] = _date_text(action.get("payment_date"))
            record["cash_effect"] = round(cash_effect, 4)
        elif action_type in {"share_distribution", "share_ratio"}:
            if action_type == "share_ratio":
                multiplier = _number(action.get("ratio"))
                additional_per_share = None if multiplier is None else multiplier - 1
            else:
                additional_per_share = _number(action.get("additional_shares_per_share"))
            if additional_per_share is None or additional_per_share <= 0:
                return {"status": "invalid", "message": "送转比例无效"}
            added_quantity = int(floor(quantity * additional_per_share))
            new_quantity = quantity + added_quantity
            if added_quantity <= 0:
                return {"status": "invalid", "message": "送转后数量无效"}
            total_cost = quantity * float(position.get("average_price") or 0)
            available_before = int(position.get("available_quantity") or 0)
            position["quantity"] = new_quantity
            position["available_quantity"] = available_before + int(
                floor(available_before * additional_per_share)
            )
            position["average_price"] = round(total_cost / new_quantity, 4)
            record["additional_shares_per_share"] = additional_per_share
            record["added_quantity"] = added_quantity
            record["bonus_shares_per_10"] = _number(action.get("bonus_shares_per_10"))
            record["transfer_shares_per_10"] = _number(action.get("transfer_shares_per_10"))
            record["shares_credit_date"] = _date_text(action.get("shares_credit_date"))
            record["quantity_after"] = new_quantity
        elif action_type == "rights_issue":
            rights_per_share = _number(action.get("rights_per_share"))
            rights_price = _number(action.get("rights_price"))
            if rights_per_share is None or rights_per_share <= 0 or rights_price is None:
                return {"status": "invalid", "message": "配股比例或价格无效"}
            record.update({
                "status": "not_subscribed",
                "rights_per_share": rights_per_share,
                "rights_per_10_shares": _number(action.get("rights_per_10_shares")),
                "rights_price": rights_price,
                "subscription_start_date": _date_text(action.get("subscription_start_date")),
                "subscription_end_date": _date_text(action.get("subscription_end_date")),
                "listing_date": _date_text(action.get("listing_date")),
                "note": "配股需要投资者主动认购，模拟账户未自动扣款或增加股份",
            })
        else:
            return {"status": "invalid", "message": f"不支持的公司行为类型: {action_type}"}
        account.setdefault("corporate_actions", []).append(record)
        account["corporate_actions"] = account["corporate_actions"][-2000:]
        event_type = (
            "corporate_action_recorded"
            if action_type == "rights_issue"
            else "corporate_action_applied"
        )
        append_audit_event(account, event_type, record)
        if action_type == "rights_issue":
            append_alert(
                account,
                code=f"RIGHTS_ISSUE_NOT_SUBSCRIBED:{action_id}",
                severity="warning",
                message=f"{symbol} 配股未自动认购，请人工决定是否参与",
                details=record,
            )
            return {"status": "not_subscribed", "record": record}
        return {"status": "ok", "record": record}

    def _sync_corporate_actions(self, account: dict[str, Any], as_of: str) -> dict[str, Any]:
        positions = account.get("positions") or {}
        if not positions:
            return {
                "status": "no_positions",
                "symbols_checked": 0,
                "events_due": 0,
                "applied": 0,
                "duplicates": 0,
                "rights_not_subscribed": 0,
                "errors": [],
            }
        result = {
            "status": "ok",
            "symbols_checked": 0,
            "events_due": 0,
            "applied": 0,
            "duplicates": 0,
            "rights_not_subscribed": 0,
            "errors": [],
            "sources": [],
        }
        for symbol, position in list(positions.items()):
            result["symbols_checked"] += 1
            try:
                source_result = self.corporate_action_service.get_due_events(
                    symbol,
                    as_of_date=as_of,
                    held_since=_date_text(position.get("buy_date")),
                )
            except Exception as exc:
                result["errors"].append(f"{symbol}: 公司行为读取失败:{exc}")
                result["sources"].append({
                    "symbol": symbol,
                    "status": "source_failed",
                    "source": None,
                    "cache_hit": False,
                    "due_event_count": 0,
                })
                continue
            source_status = str(source_result.get("status") or "source_failed")
            result["sources"].append({
                "symbol": symbol,
                "status": source_status,
                "source": source_result.get("source"),
                "cache_hit": bool(source_result.get("cache_hit")),
                "due_event_count": int(source_result.get("due_event_count") or 0),
            })
            for error in source_result.get("errors") or []:
                result["errors"].append(f"{symbol}: {error}")
            due_events = source_result.get("events") or []
            result["events_due"] += len(due_events)
            for event in due_events:
                applied = self._apply_corporate_action_to_account(account, event)
                status = applied.get("status")
                if status == "ok":
                    result["applied"] += 1
                elif status == "not_subscribed":
                    result["rights_not_subscribed"] += 1
                elif status == "duplicate":
                    result["duplicates"] += 1
                elif status not in {"ignored"}:
                    result["errors"].append(
                        f"{symbol}: {applied.get('message') or '公司行为处理失败'}"
                    )
        if result["errors"]:
            source_failures = sum(
                1 for source in result["sources"] if source.get("status") == "source_failed"
            )
            result["status"] = (
                "source_failed"
                if source_failures == result["symbols_checked"]
                else "partial_failed"
            )
        return result

    def _process_pending_buys(self, account: dict[str, Any], as_of: str) -> dict[str, int]:
        result = {"checked": 0, "filled": 0, "expired": 0, "pending": 0, "rejected": 0}
        for order in account.get("orders") or []:
            if order.get("side") != "BUY" or order.get("status") != "pending":
                continue
            scheduled = str(order.get("scheduled_date") or "")[:10]
            if scheduled and scheduled > as_of:
                result["pending"] += 1
                continue
            result["checked"] += 1
            frame, source = self._load_real_frame(str(order.get("symbol") or ""))
            if frame is None or frame.empty:
                order["last_error"] = "真实日K不可用，订单保持等待"
                result["pending"] += 1
                continue
            rows = frame[(frame["_date"] >= scheduled) & (frame["_date"] <= as_of)]
            if rows.empty:
                result["pending"] += 1
                continue
            row = rows.iloc[0]
            row_date = str(row["_date"])[:10]
            previous = frame[frame["_date"] < row_date].tail(1)
            previous_close = _number(previous.iloc[0]["close"]) if not previous.empty else None
            open_price = _number(row.get("open"))
            high = _number(row.get("high"))
            low = _number(row.get("low"))
            volume = _number(row.get("volume"))
            if None in (open_price, high, low) or volume in (None, 0):
                self._expire_order(account, order, row_date, "停牌或入场日价格无效")
                result["expired"] += 1
                continue
            if (
                previous_close is not None
                and open_price / previous_close - 1 >= 0.095
                and open_price == high == low
            ):
                self._expire_order(account, order, row_date, "涨停一字板，真实市场无法买入")
                result["expired"] += 1
                continue
            buy_low = float(order["buy_zone_low"])
            buy_high = float(order["buy_zone_high"])
            if high < buy_low or low > buy_high:
                self._expire_order(account, order, row_date, "计划入场日未触及买入区间")
                result["expired"] += 1
                continue
            fill_price = min(max(open_price, buy_low), buy_high)
            quantity = self._affordable_quantity(
                cash=float(account.get("cash") or 0),
                requested=int(order.get("quantity") or 0),
                price=fill_price,
            )
            if quantity < LOT_SIZE:
                self._reject_order(account, order, row_date, "现金不足一个100股整数手")
                result["rejected"] += 1
                continue
            gross = fill_price * quantity
            amount = _number(row.get("amount"))
            daily_amount = amount if amount is not None and amount > 0 else (close_or_open(row) * volume)
            risk_decision = self.risk_engine.evaluate_entry(
                account,
                order_notional=gross,
                industry=order.get("industry"),
                daily_amount=daily_amount,
                market_date=row_date,
                as_of_date=as_of,
                equity=self._estimate_equity(account, row_date),
            )
            order["risk_decision"] = risk_decision
            if not risk_decision["allowed"]:
                self._reject_order(
                    account,
                    order,
                    row_date,
                    "；".join(risk_decision["reasons"]),
                )
                result["rejected"] += 1
                continue
            fee = _buy_fee(gross)
            account["cash"] = round(float(account.get("cash") or 0) - gross - fee, 4)
            fill = self._record_fill(
                account,
                order,
                side="BUY",
                quantity=quantity,
                price=fill_price,
                fee=fee,
                trade_date=row_date,
                source=source,
                evidence=f"真实日K开盘价={open_price:.3f}，区间={low:.3f}-{high:.3f}",
            )
            order.update({
                "filled_quantity": quantity,
                "filled_price": round(fill_price, 3),
                "filled_at": fill["filled_at"],
                "trade_date": row_date,
                "fee": round(fee, 4),
            })
            transition_order(
                account,
                order,
                "filled",
                occurred_at=fill["filled_at"],
                details={"quantity": quantity, "price": round(fill_price, 3), "fee": round(fee, 4)},
            )
            account.setdefault("positions", {})[order["symbol"]] = {
                "symbol": order["symbol"],
                "name": order.get("name") or order["symbol"],
                "industry": order.get("industry") or "未知行业",
                "strategy": order.get("strategy"),
                "strategy_version": order.get("strategy_version"),
                "strategy_rule_id": order.get("strategy_rule_id"),
                "plan_identity": order.get("plan_identity"),
                "buy_order_id": order.get("order_id"),
                "buy_fill_id": fill.get("fill_id"),
                "quantity": quantity,
                "available_quantity": 0,
                "average_price": round(fill_price, 3),
                "buy_fee": round(fee, 4),
                "buy_date": row_date,
                "stop_loss": order.get("stop_loss"),
                "take_profit_1": order.get("take_profit_1"),
                "max_holding_days": order.get("max_holding_days") or 5,
                "price_source": source,
            }
            append_audit_event(
                account,
                "position_opened",
                {
                    "symbol": order["symbol"],
                    "quantity": quantity,
                    "average_price": round(fill_price, 3),
                    "buy_date": row_date,
                    "strategy": order.get("strategy"),
                    "strategy_version": order.get("strategy_version"),
                    "strategy_rule_id": order.get("strategy_rule_id"),
                },
                occurred_at=fill["filled_at"],
            )
            result["filled"] += 1
        return result

    def _process_position_exits(self, account: dict[str, Any], as_of: str) -> dict[str, int]:
        result = {"checked": 0, "filled": 0, "blocked_limit_down": 0, "holding": 0}
        for symbol, position in list((account.get("positions") or {}).items()):
            result["checked"] += 1
            frame, source = self._load_real_frame(symbol)
            if frame is None or frame.empty:
                result["holding"] += 1
                continue
            buy_date = str(position.get("buy_date") or "")[:10]
            rows = frame[(frame["_date"] > buy_date) & (frame["_date"] <= as_of)]
            if rows.empty:
                position["available_quantity"] = 0
                result["holding"] += 1
                continue
            position["available_quantity"] = int(position.get("quantity") or 0)
            resolved = self._resolve_exit(frame, rows, position)
            if resolved is None:
                result["holding"] += 1
                continue
            if resolved.get("blocked_limit_down"):
                position["last_exit_block"] = resolved
                result["blocked_limit_down"] += 1
                result["holding"] += 1
                continue
            quantity = int(position.get("quantity") or 0)
            price = float(resolved["price"])
            gross = price * quantity
            fee = _sell_fee(gross)
            proceeds = gross - fee
            account["cash"] = round(float(account.get("cash") or 0) + proceeds, 4)
            sell_order_id = _stable_id(
                self.account_id,
                str(position.get("plan_identity") or ""),
                symbol,
                "SELL",
                str(resolved["trade_date"]),
            )
            sell_order = {
                "order_id": sell_order_id,
                "plan_identity": position.get("plan_identity"),
                "strategy": position.get("strategy"),
                "strategy_version": position.get("strategy_version"),
                "strategy_rule_id": position.get("strategy_rule_id"),
                "symbol": symbol,
                "name": position.get("name") or symbol,
                "side": "SELL",
                "order_type": "EXIT_RULE",
                "status": "pending",
                "quantity": quantity,
                "filled_quantity": quantity,
                "filled_price": round(price, 3),
                "trade_date": resolved["trade_date"],
                "filled_at": _now(),
                "fee": round(fee, 4),
                "reason": resolved["reason"],
            }
            account.setdefault("orders", []).append(sell_order)
            append_audit_event(
                account,
                "order_created",
                {
                    "order_id": sell_order_id,
                    "strategy": position.get("strategy"),
                    "strategy_version": position.get("strategy_version"),
                    "strategy_rule_id": position.get("strategy_rule_id"),
                    "symbol": symbol,
                    "side": "SELL",
                    "quantity": quantity,
                    "reason": resolved["reason"],
                },
            )
            fill = self._record_fill(
                account,
                sell_order,
                side="SELL",
                quantity=quantity,
                price=price,
                fee=fee,
                trade_date=resolved["trade_date"],
                source=source,
                evidence=resolved["evidence"],
            )
            transition_order(
                account,
                sell_order,
                "filled",
                occurred_at=fill["filled_at"],
                details={"quantity": quantity, "price": round(price, 3), "fee": round(fee, 4)},
            )
            cost = float(position.get("average_price") or 0) * quantity + float(position.get("buy_fee") or 0)
            pnl = proceeds - cost
            return_pct = pnl / cost * 100 if cost > 0 else None
            closed = {
                "trade_id": _stable_id(position.get("buy_fill_id"), fill.get("fill_id")),
                "symbol": symbol,
                "name": position.get("name") or symbol,
                "industry": position.get("industry") or "未知行业",
                "strategy": position.get("strategy"),
                "strategy_version": position.get("strategy_version"),
                "strategy_rule_id": position.get("strategy_rule_id"),
                "plan_identity": position.get("plan_identity"),
                "quantity": quantity,
                "buy_date": buy_date,
                "buy_price": position.get("average_price"),
                "buy_fee": position.get("buy_fee"),
                "sell_date": resolved["trade_date"],
                "sell_price": round(price, 3),
                "sell_fee": round(fee, 4),
                "pnl": round(pnl, 4),
                "return_pct": round(return_pct, 4) if return_pct is not None else None,
                "is_win": pnl > 0,
                "exit_reason": resolved["reason"],
                "price_source": source,
            }
            account.setdefault("closed_trades", []).append(closed)
            account["realized_pnl"] = round(float(account.get("realized_pnl") or 0) + pnl, 4)
            account["positions"].pop(symbol, None)
            append_audit_event(
                account,
                "position_closed",
                {
                    "trade_id": closed["trade_id"],
                    "symbol": symbol,
                    "quantity": quantity,
                    "pnl": closed["pnl"],
                    "return_pct": closed["return_pct"],
                    "strategy_version": closed.get("strategy_version"),
                    "strategy_rule_id": closed.get("strategy_rule_id"),
                    "sell_date": resolved["trade_date"],
                    "exit_reason": resolved["reason"],
                },
                occurred_at=fill["filled_at"],
            )
            result["filled"] += 1
        return result

    def _resolve_exit(
        self,
        frame: pd.DataFrame,
        rows: pd.DataFrame,
        position: dict[str, Any],
    ) -> dict[str, Any] | None:
        stop_loss = _number(position.get("stop_loss"))
        take_profit = _number(position.get("take_profit_1"))
        max_holding_days = max(1, int(_number(position.get("max_holding_days")) or 5))
        blocked_exit = None
        pending_exit_reason = None
        for holding_index, (_, row) in enumerate(rows.iterrows(), start=1):
            row_date = str(row["_date"])[:10]
            open_price = _number(row.get("open"))
            high = _number(row.get("high"))
            low = _number(row.get("low"))
            close = _number(row.get("close"))
            previous = frame[frame["_date"] < row_date].tail(1)
            previous_close = _number(previous.iloc[0]["close"]) if not previous.empty else None
            if None in (open_price, high, low, close):
                continue
            one_price_limit_down = (
                previous_close is not None
                and open_price / previous_close - 1 <= -0.095
                and open_price == high == low
            )
            stop_hit = stop_loss is not None and low <= stop_loss
            target_hit = take_profit is not None and high >= take_profit
            holding_period_ended = holding_index >= max_holding_days
            exit_triggered = (
                pending_exit_reason is not None
                or stop_hit
                or target_hit
                or holding_period_ended
            )
            if one_price_limit_down and exit_triggered:
                if pending_exit_reason is None:
                    if stop_hit:
                        pending_exit_reason = "止损已触发"
                    elif target_hit:
                        pending_exit_reason = "止盈已触发"
                    else:
                        pending_exit_reason = f"持有已满{max_holding_days}个交易日"
                blocked_exit = {
                    "blocked_limit_down": True,
                    "trade_date": row_date,
                    "reason": "跌停一字板，真实市场无法卖出",
                    "evidence": f"真实日K一字跌停={open_price:.3f}",
                }
                continue
            if pending_exit_reason is not None:
                return _exit(
                    open_price,
                    row_date,
                    f"{pending_exit_reason}后首个可交易日开盘退出",
                    open_price,
                    low,
                    high,
                )
            if stop_loss is not None and open_price <= stop_loss:
                return _exit(open_price, row_date, "止损跳空退出", open_price, low, high)
            if take_profit is not None and open_price >= take_profit:
                return _exit(open_price, row_date, "止盈跳空退出", open_price, low, high)
            if stop_hit:
                reason = "同日同时触及止损和止盈，按保守口径止损" if target_hit else "触及止损退出"
                return _exit(stop_loss, row_date, reason, open_price, low, high)
            if target_hit:
                return _exit(take_profit, row_date, "触及第一止盈位退出", open_price, low, high)
            if holding_period_ended:
                return _exit(close, row_date, f"持有{max_holding_days}个交易日收盘退出", open_price, low, high)
        return blocked_exit

    def _summarize(self, account: dict[str, Any], as_of: str) -> dict[str, Any]:
        position_rows = []
        market_value = 0.0
        unrealized_pnl = 0.0
        for symbol, position in (account.get("positions") or {}).items():
            frame, source = self._load_real_frame(symbol)
            mark = None
            mark_date = None
            if frame is not None and not frame.empty:
                rows = frame[frame["_date"] <= as_of]
                if not rows.empty:
                    row = rows.iloc[-1]
                    mark = _number(row.get("close"))
                    mark_date = str(row.get("_date") or "")[:10]
            quantity = int(position.get("quantity") or 0)
            value = (mark or 0) * quantity
            cost = float(position.get("average_price") or 0) * quantity + float(position.get("buy_fee") or 0)
            pnl = value - cost if mark is not None else None
            market_value += value
            if pnl is not None:
                unrealized_pnl += pnl
            position["mark_price"] = round(mark, 3) if mark is not None else None
            position["mark_date"] = mark_date
            position["mark_source"] = source
            position_rows.append({
                **position,
                "mark_price": round(mark, 3) if mark is not None else None,
                "mark_date": mark_date,
                "market_value": round(value, 2),
                "unrealized_pnl": round(pnl, 2) if pnl is not None else None,
                "mark_source": source,
            })
        cash = float(account.get("cash") or 0)
        equity = cash + market_value
        closed = account.get("closed_trades") or []
        wins = sum(bool(row.get("is_win")) for row in closed)
        returns = [
            float(row["return_pct"])
            for row in closed
            if _number(row.get("return_pct")) is not None
        ]
        return {
            "version": account.get("version"),
            "account_id": account.get("account_id"),
            "as_of_date": as_of,
            "initial_cash": round(float(account.get("initial_cash") or 0), 2),
            "cash": round(cash, 2),
            "market_value": round(market_value, 2),
            "equity": round(equity, 2),
            "total_return_pct": (
                round((equity / float(account.get("initial_cash")) - 1) * 100, 4)
                if float(account.get("initial_cash") or 0) > 0
                else None
            ),
            "realized_pnl": round(float(account.get("realized_pnl") or 0), 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "open_positions": len(position_rows),
            "pending_orders": sum(
                order.get("status") == "pending" for order in account.get("orders") or []
            ),
            "fills": len(account.get("fills") or []),
            "closed_trades": len(closed),
            "wins": wins,
            "win_rate_pct": round(wins / len(closed) * 100, 2) if closed else None,
            "avg_return_pct": round(sum(returns) / len(returns), 4) if returns else None,
            "strategy_control": dict(self._ensure_strategy_control(account)),
            "strategy_performance": _strategy_performance_rows(closed),
            "positions": position_rows,
            "orders": list(reversed((account.get("orders") or [])[-200:])),
            "recent_fills": list(reversed((account.get("fills") or [])[-200:])),
            "recent_closed_trades": list(reversed(closed[-200:])),
            "risk": self.risk_engine.summary(account),
            "open_alerts": [
                row
                for row in reversed((account.get("alerts") or [])[-200:])
                if row.get("status") == "open"
            ],
            "alerts": list(reversed((account.get("alerts") or [])[-200:])),
            "audit": verify_audit_chain(account.get("audit_events") or []),
            "recent_audit_events": list(reversed((account.get("audit_events") or [])[-200:])),
            "last_reconciliation": (
                (account.get("reconciliations") or [])[-1]
                if account.get("reconciliations")
                else None
            ),
            "equity_curve": list((account.get("equity_curve") or [])[-1000:]),
            "corporate_actions": list(reversed((account.get("corporate_actions") or [])[-200:])),
            "last_corporate_action_sync": account.get("last_corporate_action_sync"),
            "allowed_strategies": sorted(self.allowed_strategies),
            "fee_model": {
                "commission_rate": COMMISSION_RATE,
                "minimum_commission": MIN_COMMISSION,
                "stamp_duty_sell_rate": STAMP_DUTY_RATE,
                "transfer_fee_rate": TRANSFER_FEE_RATE,
            },
            "last_reconciled_date": account.get("last_reconciled_date"),
            "last_reconciled_at": account.get("last_reconciled_at"),
        }

    def _load_real_frame(self, symbol: str) -> tuple[pd.DataFrame | None, str | None]:
        directory = self.cache_dir / "strategy_kline_daily"
        candidates = []
        for period in ("1y", "6mo", "3mo"):
            candidates.extend(directory.glob(f"CN_{symbol}_{period}_1d_*.json"))
        frames = []
        for path in candidates:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                frame = pd.DataFrame(payload["data"], columns=payload["columns"])
                frame.index = pd.to_datetime(payload["index"], errors="coerce")
                frame = frame[frame.index.notna()].sort_index()
                frame.columns = [str(column).lower() for column in frame.columns]
                for column in ("open", "high", "low", "close", "volume", "amount"):
                    if column not in frame.columns:
                        continue
                    frame[column] = pd.to_numeric(frame[column], errors="coerce")
                frame["_date"] = frame.index.astype(str).str[:10]
                if not frame.empty:
                    frames.append((frame.index.max(), len(frame), path, frame))
            except Exception:
                continue
        if not frames:
            return None, None
        _, _, path, frame = max(frames, key=lambda item: (item[0], item[1]))
        return frame, f"策略K线本地真实缓存/{path.name}"

    def _record_fill(
        self,
        account: dict[str, Any],
        order: dict[str, Any],
        *,
        side: str,
        quantity: int,
        price: float,
        fee: float,
        trade_date: str,
        source: str | None,
        evidence: str,
    ) -> dict[str, Any]:
        fill = {
            "fill_id": _stable_id(order.get("order_id"), trade_date, side, quantity, price),
            "order_id": order.get("order_id"),
            "plan_identity": order.get("plan_identity"),
            "strategy": order.get("strategy"),
            "strategy_version": order.get("strategy_version"),
            "strategy_rule_id": order.get("strategy_rule_id"),
            "symbol": order.get("symbol"),
            "name": order.get("name"),
            "side": side,
            "quantity": quantity,
            "price": round(price, 3),
            "gross_amount": round(price * quantity, 4),
            "fee": round(fee, 4),
            "trade_date": trade_date,
            "filled_at": _now(),
            "price_source": source,
            "price_evidence": evidence,
            "is_real_market_observation": True,
            "execution_model": "真实日K区间触发的模拟成交，非逐笔成交回放",
        }
        account.setdefault("fills", []).append(fill)
        append_audit_event(
            account,
            "fill_recorded",
            {
                "fill_id": fill["fill_id"],
                "order_id": fill["order_id"],
                "symbol": fill["symbol"],
                "side": side,
                "quantity": quantity,
                "price": fill["price"],
                "fee": fill["fee"],
                "trade_date": trade_date,
                "price_source": source,
            },
            occurred_at=fill["filled_at"],
        )
        return fill

    def _affordable_quantity(self, *, cash: float, requested: int, price: float) -> int:
        quantity = floor(max(0, requested) / LOT_SIZE) * LOT_SIZE
        while quantity >= LOT_SIZE:
            gross = price * quantity
            if gross + _buy_fee(gross) <= cash:
                return quantity
            quantity -= LOT_SIZE
        return 0

    @staticmethod
    def _expire_order(
        account: dict[str, Any],
        order: dict[str, Any],
        trade_date: str,
        reason: str,
    ) -> None:
        order.update({
            "closed_at": _now(),
            "trade_date": trade_date,
        })
        transition_order(account, order, "expired", reason=reason)

    @staticmethod
    def _reject_order(
        account: dict[str, Any],
        order: dict[str, Any],
        trade_date: str,
        reason: str,
    ) -> None:
        order.update({
            "closed_at": _now(),
            "trade_date": trade_date,
        })
        transition_order(account, order, "rejected", reason=reason)

    def _new_account(self) -> dict[str, Any]:
        now = _now()
        account = {
            "version": PAPER_ACCOUNT_VERSION,
            "account_id": self.account_id,
            "strategy": ",".join(sorted(self.allowed_strategies)),
            "created_at": now,
            "updated_at": now,
            "initial_cash": round(self.initial_cash, 4),
            "cash": round(self.initial_cash, 4),
            "realized_pnl": 0.0,
            "positions": {},
            "orders": [],
            "fills": [],
            "closed_trades": [],
            "corporate_actions": [],
            "last_corporate_action_sync": None,
            "synced_plan_ids": [],
            "plan_syncs": [],
            "equity_curve": [],
            "reconciliations": [],
            "alerts": [],
            "audit_events": [],
            "risk_state": {
                "manual_halt": False,
                "block_new_entries": False,
                "liquidation_required": False,
                "automatic_breaches": [],
            },
            "strategy_control": self._default_strategy_control(),
            "constraints": {
                "lot_size": LOT_SIZE,
                "t_plus_one": True,
                "max_positions": self.max_positions,
                "position_pct": self.position_pct,
                "allowed_strategies": sorted(self.allowed_strategies),
            },
        }
        append_audit_event(
            account,
            "account_created",
            {
                "account_id": self.account_id,
                "initial_cash": round(self.initial_cash, 4),
                "allowed_strategies": sorted(self.allowed_strategies),
            },
            occurred_at=now,
        )
        return account

    def _migrate_account(self, account: dict[str, Any]) -> dict[str, Any]:
        previous_version = account.get("version")
        account["version"] = PAPER_ACCOUNT_VERSION
        account.setdefault("corporate_actions", [])
        account.setdefault("last_corporate_action_sync", None)
        account.setdefault("equity_curve", [])
        account.setdefault("reconciliations", [])
        account.setdefault("alerts", [])
        account.setdefault("audit_events", [])
        account.setdefault("risk_state", {
            "manual_halt": False,
            "block_new_entries": False,
            "liquidation_required": False,
            "automatic_breaches": [],
        })
        account.setdefault("strategy_control", self._default_strategy_control())
        constraints = account.setdefault("constraints", {})
        constraints.pop("candidate_strategy_only", None)
        constraints["allowed_strategies"] = sorted(self.allowed_strategies)
        append_audit_event(
            account,
            "account_migrated",
            {
                "from_version": previous_version,
                "to_version": PAPER_ACCOUNT_VERSION,
                "opening_state": {
                    "cash": account.get("cash"),
                    "orders": len(account.get("orders") or []),
                    "fills": len(account.get("fills") or []),
                    "positions": len(account.get("positions") or {}),
                    "closed_trades": len(account.get("closed_trades") or []),
                },
            },
        )
        return account

    def _apply_strategy_rotation(self, account: dict[str, Any]) -> dict[str, Any]:
        if not self.strategy_rotation_enabled:
            return {"action": "disabled", "reason": "非正式实验模拟账户不执行自动换策略"}
        control = self._ensure_strategy_control(account)
        decision = build_rotation_decision(
            control,
            account.get("closed_trades") or [],
            load_strategy_research(
                self.cache_dir / "candidate_strategy_research_5y_latest.json"
            ),
        )
        control["last_evaluated_at"] = _now()
        control["last_metrics"] = decision.get("metrics") or {}
        control["reason"] = decision.get("reason")
        action = decision.get("action")
        if action in {"observe", "keep"}:
            control["status"] = "observing" if action == "observe" else "active"
            return decision
        if (
            action == "cash"
            and control.get("status") == "cash"
            and not control.get("active_rule_id")
        ):
            return decision

        old_rule_id = str(control.get("active_rule_id") or "")
        old_version = str(control.get("active_strategy_version") or "")
        control["failed_rule_versions"] = decision.get(
            "failed_rule_versions",
            control.get("failed_rule_versions") or [],
        )
        cancelled = self._cancel_pending_rule_orders(
            account,
            rule_id=old_rule_id,
            strategy_version=old_version,
            reason="模拟盘扣费后策略失效，停止新开仓",
        )
        next_rule = decision.get("next_rule") if action == "switch" else None
        if isinstance(next_rule, dict):
            control.update({
                "status": "observing",
                "active_rule_id": next_rule.get("rule_id"),
                "active_strategy_version": next_rule.get("strategy_version"),
                "activated_at": _now(),
                "rule_fingerprint": next_rule.get("rule_fingerprint"),
            })
        else:
            control.update({
                "status": "cash",
                "active_rule_id": None,
                "active_strategy_version": None,
                "activated_at": None,
                "rule_fingerprint": None,
            })
        event = {
            "action": action,
            "from_rule_id": old_rule_id,
            "from_strategy_version": old_version,
            "to_rule_id": control.get("active_rule_id"),
            "to_strategy_version": control.get("active_strategy_version"),
            "cancelled_pending_orders": cancelled,
            "metrics": decision.get("metrics") or {},
            "reason": decision.get("reason"),
            "occurred_at": _now(),
        }
        control.setdefault("history", []).append(event)
        control["history"] = control["history"][-100:]
        append_audit_event(account, "strategy_rotation", event)
        append_alert(
            account,
            code="EXPERIMENTAL_STRATEGY_ROTATED",
            severity="warning",
            message=decision.get("reason") or "实验策略版本已调整",
            details=event,
        )
        return {**decision, "cancelled_pending_orders": cancelled}

    @staticmethod
    def _cancel_pending_rule_orders(
        account: dict[str, Any],
        *,
        rule_id: str,
        strategy_version: str,
        reason: str,
    ) -> int:
        cancelled = 0
        for order in account.get("orders") or []:
            if (
                order.get("side") == "BUY"
                and order.get("status") == "pending"
                and str(order.get("strategy_rule_id") or "") == rule_id
                and str(order.get("strategy_version") or "") == strategy_version
            ):
                transition_order(account, order, "cancelled", reason=reason)
                cancelled += 1
        return cancelled

    @staticmethod
    def _default_strategy_control() -> dict[str, Any]:
        return {
            "status": "observing",
            "active_rule_id": EXPERIMENTAL_RULE_ID,
            "active_strategy_version": EXPERIMENTAL_STRATEGY_VERSION,
            "activated_at": _now(),
            "rule_fingerprint": None,
            "failed_rule_versions": [],
            "history": [],
            "last_metrics": {},
            "reason": "当前规则至少结算30笔后才评估是否切换",
        }

    def _ensure_strategy_control(self, account: dict[str, Any]) -> dict[str, Any]:
        control = account.get("strategy_control")
        if not isinstance(control, dict):
            control = self._default_strategy_control()
            account["strategy_control"] = control
        current = (
            str(control.get("active_strategy_version") or ""),
            str(control.get("active_rule_id") or ""),
        )
        if current in LEGACY_EXPERIMENTAL_RULE_VERSIONS:
            cancelled = self._cancel_pending_rule_orders(
                account,
                rule_id=current[1],
                strategy_version=current[0],
                reason="实验策略升级为量额换手v3，旧规则待买单作废",
            )
            event = {
                "action": "version_upgrade",
                "from_strategy_version": current[0],
                "from_rule_id": current[1],
                "to_strategy_version": EXPERIMENTAL_STRATEGY_VERSION,
                "to_rule_id": EXPERIMENTAL_RULE_ID,
                "cancelled_pending_orders": cancelled,
                "reason": "按用户要求升级为成交量、成交额、换手率和市场环境联合规则",
                "occurred_at": _now(),
            }
            control.update({
                "status": "observing",
                "active_rule_id": EXPERIMENTAL_RULE_ID,
                "active_strategy_version": EXPERIMENTAL_STRATEGY_VERSION,
                "activated_at": event["occurred_at"],
                "rule_fingerprint": None,
                "reason": "v3观察版本至少结算30笔后评估是否淘汰",
            })
            control.setdefault("history", []).append(event)
            control["history"] = control["history"][-100:]
            append_audit_event(account, "strategy_rotation", event)
        return control

    def _estimate_equity(self, account: dict[str, Any], as_of: str) -> float:
        market_value = 0.0
        for symbol, position in (account.get("positions") or {}).items():
            frame, _ = self._load_real_frame(symbol)
            mark = None
            if frame is not None and not frame.empty:
                rows = frame[frame["_date"] <= as_of]
                if not rows.empty:
                    mark = _number(rows.iloc[-1].get("close"))
            if mark is None:
                mark = _number(position.get("average_price")) or 0.0
            market_value += mark * int(position.get("quantity") or 0)
        return round(float(account.get("cash") or 0) + market_value, 4)

    @staticmethod
    def _record_equity_snapshot(account: dict[str, Any], summary: dict[str, Any]) -> None:
        snapshot = {
            "date": summary.get("as_of_date"),
            "cash": summary.get("cash"),
            "market_value": summary.get("market_value"),
            "equity": summary.get("equity"),
            "open_positions": summary.get("open_positions"),
        }
        curve = account.setdefault("equity_curve", [])
        if curve and curve[-1].get("date") == snapshot["date"]:
            curve[-1] = snapshot
        else:
            curve.append(snapshot)
        account["equity_curve"] = curve[-5000:]

    @staticmethod
    def _cancel_pending_orders(account: dict[str, Any], *, reason: str) -> int:
        cancelled = 0
        for order in account.get("orders") or []:
            if order.get("status") != "pending":
                continue
            order["closed_at"] = _now()
            transition_order(account, order, "cancelled", reason=reason)
            cancelled += 1
        return cancelled

    def _save(self, account: dict[str, Any]) -> None:
        account["updated_at"] = _now()
        self.cache.set(self.account_id, account)


def _exit(
    price: float,
    trade_date: str,
    reason: str,
    open_price: float,
    low: float,
    high: float,
) -> dict[str, Any]:
    return {
        "blocked_limit_down": False,
        "price": round(price, 3),
        "trade_date": trade_date,
        "reason": reason,
        "evidence": f"真实日K开盘价={open_price:.3f}，区间={low:.3f}-{high:.3f}",
    }


def _buy_fee(gross: float) -> float:
    return max(MIN_COMMISSION, gross * COMMISSION_RATE) + gross * TRANSFER_FEE_RATE


def _sell_fee(gross: float) -> float:
    return (
        max(MIN_COMMISSION, gross * COMMISSION_RATE)
        + gross * TRANSFER_FEE_RATE
        + gross * STAMP_DUTY_RATE
    )


def _stable_id(*parts: Any) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _plan_rule_id(plan: dict[str, Any]) -> str:
    direct = str(plan.get("strategy_rule_id") or "").strip()
    if direct:
        return direct
    for stock in plan.get("recommended") or []:
        value = str((stock or {}).get("strategy_rule_id") or "").strip()
        if value:
            return value
    return ""


def _strategy_performance_rows(
    closed_trades: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in closed_trades:
        rule_id = str(row.get("strategy_rule_id") or "").strip()
        version = str(row.get("strategy_version") or "").strip()
        if rule_id and version:
            grouped.setdefault((version, rule_id), []).append(row)
    result = []
    for (version, rule_id), rows in sorted(grouped.items()):
        pnls = [float(row.get("pnl") or 0) for row in rows]
        gains = sum(value for value in pnls if value > 0)
        losses = abs(sum(value for value in pnls if value < 0))
        wins = sum(value > 0 for value in pnls)
        result.append({
            "strategy_version": version,
            "strategy_rule_id": rule_id,
            "settled_trades": len(rows),
            "wins": wins,
            "win_rate_pct": round(wins / len(rows) * 100, 2),
            "net_pnl": round(sum(pnls), 4),
            "profit_factor": round(gains / losses, 4) if losses > 0 else None,
        })
    return result


def _date_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        parsed = pd.to_datetime(value, errors="raise")
        return parsed.date().isoformat()
    except Exception:
        return None


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _round_price(value: Any) -> float | None:
    number = _number(value)
    return round(number, 3) if number is not None else None


def close_or_open(row: pd.Series) -> float:
    return _number(row.get("close")) or _number(row.get("open")) or 0.0


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None
