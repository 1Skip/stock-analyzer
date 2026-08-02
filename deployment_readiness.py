"""Non-bypassable launch sequence for research, backtest, paper, and live stages."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from broker_execution import build_broker_adapter
from config import RUNTIME_CACHE_DIR
from paper_trading import PaperTradingService


DEFAULT_RESEARCH_PATH = Path(RUNTIME_CACHE_DIR) / "candidate_strategy_research_latest.json"
DEFAULT_PORTFOLIO_PATH = Path(RUNTIME_CACHE_DIR) / "portfolio_backtest_latest.json"


class DeploymentReadinessService:
    """Evaluate launch stages; later stages cannot pass before earlier stages."""

    def __init__(
        self,
        *,
        research_path: Path = DEFAULT_RESEARCH_PATH,
        portfolio_path: Path = DEFAULT_PORTFOLIO_PATH,
    ):
        self.research_path = research_path
        self.portfolio_path = portfolio_path

    def evaluate(
        self,
        *,
        research: dict[str, Any] | None = None,
        portfolio: dict[str, Any] | None = None,
        paper_summary: dict[str, Any] | None = None,
        broker_readiness: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        research = research if isinstance(research, dict) else _load_json(self.research_path)
        portfolio = portfolio if isinstance(portfolio, dict) else _load_json(self.portfolio_path)
        paper = (
            paper_summary
            if isinstance(paper_summary, dict)
            else PaperTradingService().get_summary()
        )
        broker = (
            broker_readiness
            if isinstance(broker_readiness, dict)
            else build_broker_adapter().readiness()
        )

        stages = []
        research_quality = research.get("data_quality") or {}
        selected_rule = str(research.get("selected_rule_id") or "")
        research_passed = bool(
            research.get("status") == "ok"
            and selected_rule
            and research_quality.get("point_in_time_universe")
            and not research_quality.get("promotion_blockers")
        )
        stages.append(_stage(
            1,
            "策略研究转正",
            research_passed,
            "正式规则、时点股票池和研究门槛全部通过"
            if research_passed
            else _first_reason(
                research_quality.get("promotion_blockers"),
                "没有经过正式门槛选中的策略" if not selected_rule else "研究数据质量未通过",
            ),
            evidence={
                "selected_rule_id": selected_rule or None,
                "point_in_time_universe": research_quality.get("point_in_time_universe"),
            },
        ))

        portfolio_metrics = portfolio.get("metrics") or {}
        portfolio_passed_raw = bool(
            portfolio.get("status") == "ok"
            and (portfolio_metrics.get("closed_trades") or 0) >= 100
            and (portfolio_metrics.get("total_return_pct") or 0) > 0
            and (portfolio_metrics.get("excess_return_pct") or 0) > 0
            and (portfolio_metrics.get("max_drawdown_pct") or -999) > -12
            and ((portfolio.get("audit") or {}).get("valid"))
            and ((portfolio.get("reconciliation") or {}).get("status") == "ok")
        )
        portfolio_passed = research_passed and portfolio_passed_raw
        stages.append(_stage(
            2,
            "组合级回测验收",
            portfolio_passed,
            "收益、超额、回撤、样本、审计和对账全部通过"
            if portfolio_passed
            else (
                "前置策略研究未通过"
                if not research_passed
                else "组合回测尚未同时满足100笔、正收益、正超额和回撤门槛"
            ),
            evidence={
                "closed_trades": portfolio_metrics.get("closed_trades"),
                "total_return_pct": portfolio_metrics.get("total_return_pct"),
                "excess_return_pct": portfolio_metrics.get("excess_return_pct"),
                "max_drawdown_pct": portfolio_metrics.get("max_drawdown_pct"),
            },
        ))

        closed_trades = int(paper.get("closed_trades") or 0)
        distinct_plans = len({
            str(row.get("plan_identity"))
            for row in paper.get("recent_closed_trades") or []
            if row.get("plan_identity")
        })
        paper_passed_raw = bool(
            closed_trades >= 100
            and distinct_plans >= 20
            and (paper.get("win_rate_pct") or 0) >= 55
            and (paper.get("avg_return_pct") or 0) > 0
            and (paper.get("audit") or {}).get("valid")
            and (paper.get("last_reconciliation") or {}).get("status") == "ok"
            and not (paper.get("risk") or {}).get("block_new_entries")
        )
        paper_passed = portfolio_passed and paper_passed_raw
        stages.append(_stage(
            3,
            "前向模拟盘验收",
            paper_passed,
            "模拟盘样本、收益、审计、对账和风控全部通过"
            if paper_passed
            else (
                "前置组合回测未通过"
                if not portfolio_passed
                else "模拟盘尚未达到100笔、20个独立计划和55%扣费胜率"
            ),
            evidence={
                "closed_trades": closed_trades,
                "distinct_plans": distinct_plans,
                "win_rate_pct": paper.get("win_rate_pct"),
                "avg_return_pct": paper.get("avg_return_pct"),
            },
        ))

        broker_passed_raw = bool(
            broker.get("ready")
            and broker.get("live_order_enabled")
            and not broker.get("read_only")
        )
        live_passed = paper_passed and broker_passed_raw
        stages.append(_stage(
            4,
            "小资金实盘",
            live_passed,
            "前置验收通过且券商真实委托闸门已开启"
            if live_passed
            else (
                "前向模拟盘未通过"
                if not paper_passed
                else "券商环境或真实委托三重闸门未就绪"
            ),
            evidence={
                "broker_mode": broker.get("mode"),
                "broker_ready": broker.get("ready"),
                "live_order_enabled": broker.get("live_order_enabled"),
            },
        ))

        stages.append(_stage(
            5,
            "扩仓",
            False,
            "扩仓必须基于真实小资金账户的独立验收，系统不会自动放行",
            evidence={"automatic_promotion": False},
        ))
        current = next((row for row in stages if row["status"] != "passed"), stages[-1])
        return {
            "status": "ready" if all(row["status"] == "passed" for row in stages[:-1]) else "blocked",
            "current_stage": current["name"],
            "stages": stages,
            "automatic_live_promotion": False,
            "message": current["reason"],
        }


def _stage(
    order: int,
    name: str,
    passed: bool,
    reason: str,
    *,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "order": order,
        "name": name,
        "status": "passed" if passed else "blocked",
        "reason": reason,
        "evidence": evidence,
    }


def _first_reason(reasons: Any, fallback: str) -> str:
    if isinstance(reasons, list) and reasons:
        return str(reasons[0])
    return fallback


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}
