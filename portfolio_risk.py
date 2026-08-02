"""Portfolio-level risk controls shared by paper trading and backtests."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from math import isfinite
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class PortfolioRiskLimits:
    max_drawdown_pct: float = 12.0
    max_daily_loss_pct: float = 4.0
    max_industry_exposure_pct: float = 40.0
    max_order_participation_pct: float = 0.5
    max_data_age_days: int = 5


class PortfolioRiskEngine:
    """Evaluate hard portfolio limits without selecting or ranking stocks."""

    def __init__(self, limits: PortfolioRiskLimits | None = None):
        self.limits = limits or PortfolioRiskLimits()

    def update_account_state(
        self,
        account: dict[str, Any],
        *,
        equity: float,
        as_of_date: Any,
    ) -> dict[str, Any]:
        as_of = _date_text(as_of_date) or date.today().isoformat()
        risk = account.setdefault("risk_state", {})
        peak_equity = max(float(risk.get("peak_equity") or 0), float(equity))
        previous_snapshot = next(
            (
                row
                for row in reversed(account.get("equity_curve") or [])
                if str(row.get("date") or "") < as_of
            ),
            None,
        )
        previous_equity = _number((previous_snapshot or {}).get("equity"))
        drawdown_pct = (equity / peak_equity - 1) * 100 if peak_equity > 0 else 0.0
        daily_return_pct = (
            (equity / previous_equity - 1) * 100
            if previous_equity is not None and previous_equity > 0
            else None
        )
        breaches = []
        if drawdown_pct <= -abs(self.limits.max_drawdown_pct):
            breaches.append("组合最大回撤熔断")
        if daily_return_pct is not None and daily_return_pct <= -abs(self.limits.max_daily_loss_pct):
            breaches.append("组合单日亏损熔断")
        manual_halt = bool(risk.get("manual_halt"))
        risk.update({
            "as_of_date": as_of,
            "peak_equity": round(peak_equity, 4),
            "drawdown_pct": round(drawdown_pct, 4),
            "daily_return_pct": round(daily_return_pct, 4) if daily_return_pct is not None else None,
            "automatic_breaches": breaches,
            "block_new_entries": bool(manual_halt or breaches),
            "liquidation_required": bool(breaches),
            "limits": asdict(self.limits),
        })
        return risk

    def evaluate_entry(
        self,
        account: dict[str, Any],
        *,
        order_notional: float,
        industry: str | None,
        daily_amount: float | None,
        market_date: Any,
        as_of_date: Any,
        equity: float,
    ) -> dict[str, Any]:
        """Return a deterministic hard-risk decision for one proposed buy."""
        reasons: list[str] = []
        warnings: list[str] = []
        risk = account.get("risk_state") or {}
        if risk.get("block_new_entries"):
            reasons.append("账户处于禁止新开仓状态")

        market_day = _date_text(market_date)
        as_of = _date_text(as_of_date)
        data_age_days = None
        if market_day and as_of:
            data_age_days = (pd.Timestamp(as_of) - pd.Timestamp(market_day)).days
            if data_age_days > self.limits.max_data_age_days:
                reasons.append(f"行情数据已陈旧{data_age_days}天")
        else:
            reasons.append("缺少可核验的行情日期")

        participation_pct = None
        if daily_amount is None or daily_amount <= 0:
            reasons.append("缺少有效成交额，无法验证成交容量")
        else:
            participation_pct = order_notional / daily_amount * 100
            if participation_pct > self.limits.max_order_participation_pct:
                reasons.append(
                    f"订单占当日成交额{participation_pct:.3f}%，超过"
                    f"{self.limits.max_order_participation_pct:.3f}%"
                )

        normalized_industry = str(industry or "未知行业").strip() or "未知行业"
        current_exposure = 0.0
        for position in (account.get("positions") or {}).values():
            position_industry = str(position.get("industry") or "未知行业").strip() or "未知行业"
            if position_industry != normalized_industry:
                continue
            current_exposure += (
                (_number(position.get("mark_price")) or _number(position.get("average_price")) or 0.0)
                * int(_number(position.get("quantity")) or 0)
            )
        industry_exposure_pct = (
            (current_exposure + order_notional) / equity * 100
            if equity > 0
            else 100.0
        )
        if industry_exposure_pct > self.limits.max_industry_exposure_pct:
            reasons.append(
                f"{normalized_industry}暴露将达{industry_exposure_pct:.2f}%，超过"
                f"{self.limits.max_industry_exposure_pct:.2f}%"
            )
        if normalized_industry == "未知行业":
            warnings.append("行业字段缺失，按未知行业合并计算集中度")

        return {
            "allowed": not reasons,
            "reasons": reasons,
            "warnings": warnings,
            "metrics": {
                "order_notional": round(float(order_notional), 2),
                "daily_amount": round(float(daily_amount), 2) if daily_amount is not None else None,
                "participation_pct": (
                    round(participation_pct, 4) if participation_pct is not None else None
                ),
                "industry": normalized_industry,
                "industry_exposure_pct": round(industry_exposure_pct, 4),
                "data_age_days": data_age_days,
            },
        }

    def set_manual_halt(
        self,
        account: dict[str, Any],
        *,
        enabled: bool,
        reason: str,
    ) -> dict[str, Any]:
        risk = account.setdefault("risk_state", {})
        risk["manual_halt"] = bool(enabled)
        risk["manual_halt_reason"] = str(reason or "人工操作")
        risk["block_new_entries"] = bool(enabled or risk.get("automatic_breaches"))
        return risk

    def summary(self, account: dict[str, Any]) -> dict[str, Any]:
        risk = account.get("risk_state") or {}
        return {
            "manual_halt": bool(risk.get("manual_halt")),
            "manual_halt_reason": risk.get("manual_halt_reason"),
            "block_new_entries": bool(risk.get("block_new_entries")),
            "liquidation_required": bool(risk.get("liquidation_required")),
            "drawdown_pct": risk.get("drawdown_pct"),
            "daily_return_pct": risk.get("daily_return_pct"),
            "peak_equity": risk.get("peak_equity"),
            "automatic_breaches": list(risk.get("automatic_breaches") or []),
            "limits": risk.get("limits") or asdict(self.limits),
        }


def _date_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return pd.to_datetime(value, errors="raise").date().isoformat()
    except Exception:
        return None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None
