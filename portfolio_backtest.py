"""Portfolio replay using the same account, execution, and risk rules as paper trading."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from math import sqrt
from typing import Any

import pandas as pd

from paper_trading import PaperTradingService
from portfolio_risk import PortfolioRiskEngine, PortfolioRiskLimits
from quality_monitor import build_plan_history_identity
from data.services.corporate_action_service import CorporateActionService


class _MemoryCache:
    def __init__(self):
        self.values: dict[str, Any] = {}

    def get(self, key: str) -> Any:
        return self.values.get(str(key))

    def set(self, key: str, value: Any) -> None:
        self.values[str(key)] = value


class _ReplayPaperTradingService(PaperTradingService):
    def __init__(self, *, frames: dict[str, pd.DataFrame], **kwargs):
        self.frames = frames
        super().__init__(cache=_MemoryCache(), cache_dir=".", **kwargs)

    def _load_real_frame(self, symbol: str) -> tuple[pd.DataFrame | None, str | None]:
        frame = self.frames.get(str(symbol))
        if frame is None or frame.empty:
            return None, None
        return frame, "组合回测输入/真实历史日K"


class PortfolioBacktestEngine:
    """Replay saved plans through one cash-constrained portfolio."""

    def __init__(
        self,
        *,
        initial_cash: float = 1_000_000.0,
        max_positions: int = 5,
        position_pct: float = 0.18,
        risk_limits: PortfolioRiskLimits | None = None,
        corporate_action_service: CorporateActionService | None = None,
    ):
        self.initial_cash = max(0.0, float(initial_cash))
        self.max_positions = max(1, int(max_positions))
        self.position_pct = max(0.01, min(1.0, float(position_pct)))
        self.risk_limits = risk_limits or PortfolioRiskLimits()
        self.corporate_action_service = corporate_action_service or CorporateActionService()

    def run(
        self,
        plans: list[dict[str, Any]],
        frames: dict[str, pd.DataFrame],
        *,
        benchmark: pd.DataFrame | None = None,
        start_date: Any = None,
        end_date: Any = None,
    ) -> dict[str, Any]:
        prepared_frames, frame_errors = _prepare_frames(frames)
        normalized_plans, plan_errors = _normalize_plans(plans)
        if not normalized_plans:
            return self._empty_result("没有可重放的真实T+1计划", frame_errors + plan_errors)
        if not prepared_frames:
            return self._empty_result("没有可用的真实历史日K", frame_errors + plan_errors)

        start = _date_text(start_date) or min(row["plan_date"] for row in normalized_plans)
        end = _date_text(end_date) or max(
            str(frame["_date"].iloc[-1])
            for frame in prepared_frames.values()
            if not frame.empty
        )
        if start > end:
            return self._empty_result("回测开始日期晚于结束日期", frame_errors + plan_errors)

        active_plans = [row for row in normalized_plans if start <= row["plan_date"] <= end]
        strategies = {row["plan"].get("strategy") for row in active_plans if row["plan"].get("strategy")}
        service = _ReplayPaperTradingService(
            frames=prepared_frames,
            account_id="portfolio_backtest",
            initial_cash=self.initial_cash,
            max_positions=self.max_positions,
            position_pct=self.position_pct,
            allowed_strategies=strategies,
            risk_engine=PortfolioRiskEngine(self.risk_limits),
            corporate_action_service=self.corporate_action_service,
        )
        plans_by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in active_plans:
            plans_by_date[row["plan_date"]].append(row["plan"])

        calendar = sorted({
            day
            for frame in prepared_frames.values()
            for day in frame["_date"].tolist()
            if start <= day <= end
        })
        sync_results = []
        daily_rows = []
        corporate_action_errors: list[str] = []
        corporate_action_statuses: set[str] = set()
        peak_positions = 0
        for trade_date in calendar:
            for plan in plans_by_date.get(trade_date, []):
                sync_results.append({
                    "plan_date": trade_date,
                    "strategy": plan.get("strategy"),
                    **service.sync_plan(plan),
                })
            reconciliation = service.reconcile(as_of_date=trade_date)
            summary = reconciliation["summary"]
            corporate_action_result = reconciliation.get("corporate_actions") or {}
            corporate_action_statuses.add(
                str(corporate_action_result.get("status") or "source_failed")
            )
            corporate_action_errors.extend(corporate_action_result.get("errors") or [])
            peak_positions = max(peak_positions, int(summary.get("open_positions") or 0))
            daily_rows.append({
                "date": trade_date,
                "cash": summary.get("cash"),
                "market_value": summary.get("market_value"),
                "equity": summary.get("equity"),
                "open_positions": summary.get("open_positions"),
                "pending_orders": summary.get("pending_orders"),
                "drawdown_pct": (summary.get("risk") or {}).get("drawdown_pct"),
                "blocked": bool((summary.get("risk") or {}).get("block_new_entries")),
                "corporate_action_status": corporate_action_result.get("status"),
            })

        account = service.get_account()
        final_summary = service.get_summary(as_of_date=end)
        metrics = _portfolio_metrics(
            daily_rows,
            account.get("fills") or [],
            account.get("closed_trades") or [],
            initial_cash=self.initial_cash,
        )
        benchmark_result = _benchmark_metrics(benchmark, daily_rows)
        if benchmark_result.get("total_return_pct") is not None:
            metrics["benchmark_return_pct"] = benchmark_result["total_return_pct"]
            metrics["excess_return_pct"] = round(
                float(metrics["total_return_pct"]) - float(benchmark_result["total_return_pct"]),
                4,
            )
        else:
            metrics["benchmark_return_pct"] = None
            metrics["excess_return_pct"] = None

        attribution = _build_attribution(
            account.get("closed_trades") or [],
            account.get("positions") or {},
        )
        rejected = [
            order
            for order in account.get("orders") or []
            if order.get("status") in {"rejected", "expired", "cancelled"}
        ]
        return {
            "status": "ok",
            "start_date": start,
            "end_date": end,
            "source": "已保存真实T+1计划 + 真实历史日K + 巨潮公司行为 + 统一账户撮合/风控",
            "metrics": {
                **metrics,
                "peak_positions": peak_positions,
                "ending_cash": final_summary.get("cash"),
                "ending_market_value": final_summary.get("market_value"),
                "ending_equity": final_summary.get("equity"),
            },
            "benchmark": benchmark_result,
            "equity_curve": daily_rows,
            "attribution": attribution,
            "orders": list(account.get("orders") or []),
            "fills": list(account.get("fills") or []),
            "closed_trades": list(account.get("closed_trades") or []),
            "open_positions": list(final_summary.get("positions") or []),
            "corporate_actions": list(final_summary.get("corporate_actions") or []),
            "risk": final_summary.get("risk"),
            "reconciliation": final_summary.get("last_reconciliation"),
            "audit": final_summary.get("audit"),
            "sync_results": sync_results,
            "data_quality": {
                "plans_received": len(plans),
                "plans_replayed": len(active_plans),
                "symbols_with_kline": len(prepared_frames),
                "rejected_or_expired_orders": len(rejected),
                "errors": frame_errors + plan_errors,
                "survivorship_bias": True,
                "point_in_time_universe": False,
                "corporate_actions": {
                    "status": _corporate_action_quality_status(corporate_action_statuses),
                    "events_recorded": len(account.get("corporate_actions") or []),
                    "errors": list(dict.fromkeys(corporate_action_errors)),
                    "price_basis": "统一账户使用未复权真实日K，公司行为独立入账",
                },
            },
        }

    @staticmethod
    def _empty_result(message: str, errors: list[str]) -> dict[str, Any]:
        return {
            "status": "insufficient_data",
            "message": message,
            "metrics": {},
            "benchmark": {"status": "unavailable", "message": "组合回测未运行"},
            "equity_curve": [],
            "attribution": [],
            "orders": [],
            "fills": [],
            "closed_trades": [],
            "open_positions": [],
            "data_quality": {"errors": errors},
        }


def _prepare_frames(
    frames: dict[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    prepared = {}
    errors = []
    for symbol, raw in (frames or {}).items():
        if raw is None or getattr(raw, "empty", True):
            errors.append(f"{symbol}: 日K为空")
            continue
        frame = raw.copy()
        frame.columns = [str(column).lower() for column in frame.columns]
        missing = {"open", "high", "low", "close", "volume"} - set(frame.columns)
        if missing:
            errors.append(f"{symbol}: 缺少字段 {','.join(sorted(missing))}")
            continue
        if not isinstance(frame.index, pd.DatetimeIndex):
            frame.index = pd.to_datetime(frame.index, errors="coerce")
        frame = frame[frame.index.notna()].sort_index()
        for column in ("open", "high", "low", "close", "volume", "amount"):
            if column in frame.columns:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame["_date"] = frame.index.astype(str).str[:10]
        frame = frame.drop_duplicates(subset=["_date"], keep="last")
        if frame.empty:
            errors.append(f"{symbol}: 日期无效")
            continue
        prepared[str(symbol)] = frame
    return prepared, errors


def _corporate_action_quality_status(statuses: set[str]) -> str:
    relevant = statuses - {"no_positions", "ok"}
    if not relevant:
        return "ok"
    if relevant == {"source_failed"}:
        return "source_failed"
    return "partial_failed"


def _normalize_plans(
    plans: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    normalized = []
    errors = []
    seen = set()
    for index, raw in enumerate(plans or []):
        plan = raw.get("plan") if isinstance(raw, dict) and isinstance(raw.get("plan"), dict) else raw
        if not isinstance(plan, dict):
            errors.append(f"第{index + 1}个计划格式无效")
            continue
        identity = build_plan_history_identity(plan)
        if not identity or identity in seen:
            if not identity:
                errors.append(f"第{index + 1}个计划缺少稳定标识")
            continue
        plan_date = _date_text(
            plan.get("plan_for_trade_date")
            or plan.get("generated_trade_date")
            or plan.get("generated_at")
        )
        if not plan_date:
            errors.append(f"{identity}: 缺少计划交易日")
            continue
        recommended = [
            stock
            for stock in plan.get("recommended") or []
            if isinstance(stock, dict)
            and stock.get("symbol")
            and isinstance(stock.get("trade_plan"), dict)
        ]
        if not recommended:
            errors.append(f"{identity}: 没有带交易计划的候选")
            continue
        normalized_plan = {**plan, "recommended": recommended, "plan_for_trade_date": plan_date}
        normalized.append({"identity": identity, "plan_date": plan_date, "plan": normalized_plan})
        seen.add(identity)
    normalized.sort(key=lambda row: (row["plan_date"], row["identity"]))
    return normalized, errors


def _portfolio_metrics(
    curve: list[dict[str, Any]],
    fills: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    *,
    initial_cash: float,
) -> dict[str, Any]:
    if not curve:
        return {}
    series = pd.Series(
        [float(row.get("equity") or 0) for row in curve],
        index=pd.to_datetime([row["date"] for row in curve]),
        dtype=float,
    )
    series = series[~series.index.duplicated(keep="last")].sort_index()
    daily_returns = series.pct_change().dropna()
    total_return_pct = (series.iloc[-1] / initial_cash - 1) * 100 if initial_cash > 0 else 0.0
    trading_days = max(1, len(series) - 1)
    annualized_return_pct = (
        ((series.iloc[-1] / initial_cash) ** (252 / trading_days) - 1) * 100
        if initial_cash > 0 and series.iloc[-1] > 0
        else None
    )
    volatility_pct = float(daily_returns.std(ddof=0) * sqrt(252) * 100) if len(daily_returns) else 0.0
    sharpe = (
        float(daily_returns.mean() / daily_returns.std(ddof=0) * sqrt(252))
        if len(daily_returns) and daily_returns.std(ddof=0) > 0
        else None
    )
    running_peak = series.cummax()
    drawdowns = series / running_peak - 1
    gross_turnover = sum(float(fill.get("gross_amount") or 0) for fill in fills)
    average_equity = float(series.mean()) if len(series) else initial_cash
    exposures = [
        float(row.get("market_value") or 0) / float(row.get("equity") or 1)
        for row in curve
        if float(row.get("equity") or 0) > 0
    ]
    wins = sum(float(row.get("pnl") or 0) > 0 for row in trades)
    gains = sum(max(0.0, float(row.get("pnl") or 0)) for row in trades)
    losses = abs(sum(min(0.0, float(row.get("pnl") or 0)) for row in trades))
    return {
        "initial_cash": round(initial_cash, 2),
        "total_return_pct": round(total_return_pct, 4),
        "annualized_return_pct": (
            round(annualized_return_pct, 4) if annualized_return_pct is not None else None
        ),
        "max_drawdown_pct": round(float(drawdowns.min()) * 100, 4),
        "annualized_volatility_pct": round(volatility_pct, 4),
        "sharpe_ratio": round(sharpe, 4) if sharpe is not None else None,
        "turnover_ratio": round(gross_turnover / average_equity, 4) if average_equity > 0 else None,
        "average_exposure_pct": (
            round(sum(exposures) / len(exposures) * 100, 4) if exposures else 0.0
        ),
        "closed_trades": len(trades),
        "win_rate_pct": round(wins / len(trades) * 100, 2) if trades else None,
        "profit_factor": round(gains / losses, 4) if losses > 0 else None,
        "fees": round(sum(float(fill.get("fee") or 0) for fill in fills), 4),
    }


def _benchmark_metrics(
    benchmark: pd.DataFrame | None,
    curve: list[dict[str, Any]],
) -> dict[str, Any]:
    if benchmark is None or getattr(benchmark, "empty", True) or "close" not in benchmark.columns:
        return {
            "status": "unavailable",
            "symbol": "000300",
            "message": "沪深300真实历史行情不可用，基准超额不计算",
            "total_return_pct": None,
        }
    frame = benchmark.copy()
    if not isinstance(frame.index, pd.DatetimeIndex):
        frame.index = pd.to_datetime(frame.index, errors="coerce")
    close = pd.to_numeric(frame["close"], errors="coerce").dropna().sort_index()
    if not curve or close.empty:
        return {
            "status": "unavailable",
            "symbol": "000300",
            "message": "基准与组合没有可对齐日期",
            "total_return_pct": None,
        }
    start = pd.Timestamp(curve[0]["date"])
    end = pd.Timestamp(curve[-1]["date"])
    selected = close[(close.index >= start) & (close.index <= end)]
    if len(selected) < 2:
        return {
            "status": "unavailable",
            "symbol": "000300",
            "message": "基准有效样本不足2个交易日",
            "total_return_pct": None,
        }
    total_return_pct = (selected.iloc[-1] / selected.iloc[0] - 1) * 100
    drawdown_pct = float((selected / selected.cummax() - 1).min()) * 100
    return {
        "status": "ok",
        "symbol": "000300",
        "source": benchmark.attrs.get("data_source") or "真实沪深300历史行情",
        "start_date": selected.index[0].date().isoformat(),
        "end_date": selected.index[-1].date().isoformat(),
        "samples": len(selected),
        "total_return_pct": round(float(total_return_pct), 4),
        "max_drawdown_pct": round(drawdown_pct, 4),
    }


def _build_attribution(
    trades: list[dict[str, Any]],
    positions: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for trade in trades:
        key = (
            str(trade.get("strategy") or "--"),
            str(trade.get("industry") or "未知行业"),
        )
        bucket = buckets.setdefault(key, {"trades": 0, "wins": 0, "realized_pnl": 0.0})
        bucket["trades"] += 1
        bucket["wins"] += bool(trade.get("is_win"))
        bucket["realized_pnl"] += float(trade.get("pnl") or 0)
    for position in positions.values():
        key = (
            str(position.get("strategy") or "--"),
            str(position.get("industry") or "未知行业"),
        )
        bucket = buckets.setdefault(key, {"trades": 0, "wins": 0, "realized_pnl": 0.0})
        bucket["open_market_value"] = float(bucket.get("open_market_value") or 0) + (
            float(position.get("mark_price") or position.get("average_price") or 0)
            * int(position.get("quantity") or 0)
        )
    rows = []
    for (strategy, industry), values in buckets.items():
        rows.append({
            "strategy": strategy,
            "industry": industry,
            "closed_trades": values["trades"],
            "win_rate_pct": (
                round(values["wins"] / values["trades"] * 100, 2)
                if values["trades"]
                else None
            ),
            "realized_pnl": round(values["realized_pnl"], 2),
            "open_market_value": round(float(values.get("open_market_value") or 0), 2),
        })
    return sorted(rows, key=lambda row: (-row["realized_pnl"], row["strategy"], row["industry"]))


def _date_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return pd.to_datetime(value, errors="raise").date().isoformat()
    except Exception:
        return None
