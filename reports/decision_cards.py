"""Markdown renderers for trade plan and defense dashboard push content."""
from __future__ import annotations

from typing import Any

from ui.decision_dashboard import build_defense_dashboard, build_trade_plan


def build_decision_card_markdown(
    decision: dict[str, Any],
    *,
    data: Any = None,
    extended_info: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    compact: bool = False,
) -> list[str]:
    """Render the web trade plan/defense dashboard as concise Markdown lines."""
    if not decision:
        return []

    trade_plan = build_trade_plan(decision, data)
    defense = build_defense_dashboard(
        decision,
        data=data,
        extended_info=extended_info or {},
        profile=profile or {},
    )
    state = defense.get("signal_state") or {}
    metrics = {item.get("name"): item for item in defense.get("core_metrics", [])}
    capital_rows = defense.get("capital_trace", [])
    risk_control = decision.get("risk_control") or {}

    lines = [
        "- **交易计划卡片**："
        f"当前动作 **{_text(trade_plan.get('current_action'))}**；"
        f"买入观察区 {_text(trade_plan.get('buy_zone'))}；"
        f"加仓确认 {_text(trade_plan.get('add_condition'))}；"
        f"止损线 {_level(trade_plan.get('stop_loss'))}；"
        f"第一压力 {_level(trade_plan.get('take_profit_1'))}；"
        f"建议仓位 **{_text(trade_plan.get('position'))}**。",
        "- **风控防御看板**："
        f"总分 **{defense.get('overall', '--')}/100**；"
        f"状态 **{_text(state.get('name'))}**；"
        f"{_text(defense.get('conclusion'))}；"
        f"{_text(state.get('reason'))}。",
    ]

    if risk_control:
        lines.append(
            "- **执行风控 Agent**："
            f"动作 **{_text(risk_control.get('final_action'))}**；"
            f"仓位上限 **{_text(risk_control.get('max_position'))}**；"
            f"硬拦截 {'已触发' if risk_control.get('hard_block') else '未触发'}；"
            f"止损线 {_level(risk_control.get('stop_loss'))}。"
        )
        if risk_control.get("reduce_triggers"):
            triggers = "；".join(str(item) for item in risk_control["reduce_triggers"][:2 if compact else 4])
            lines.append(f"  - 风控触发：{triggers}")
        if risk_control.get("basis"):
            basis = "；".join(str(item) for item in risk_control["basis"][:2 if compact else 4])
            lines.append(f"  - 风控依据：{basis}")

    if state.get("triggers"):
        triggers = "；".join(str(item) for item in state["triggers"][:2 if compact else 4])
        lines.append(f"  - 下一触发：{triggers}")

    metric_names = ["PEG", "相对强弱", "主力成本", "资金态度"] if compact else [
        "PEG",
        "相对强弱",
        "Beta",
        "股息率",
        "主力成本",
        "资金态度",
        "60日收益",
        "最大回撤",
    ]
    metric_text = "；".join(
        f"{name} {metrics[name].get('value', '暂无')}"
        for name in metric_names
        if name in metrics
    )
    if metric_text:
        lines.append(f"  - 核心指标：{metric_text}")

    if capital_rows:
        selected_rows = capital_rows[:3 if compact else 6]
        capital_text = "；".join(
            f"{row.get('label')} {row.get('value')}（{row.get('impact')}）"
            for row in selected_rows
        )
        lines.append(f"  - 资金博弈溯源：{capital_text}")

    lines.append(f"  - 数据说明：{_text(defense.get('data_basis'))}")
    return lines


def _text(value: Any) -> str:
    if value is None or value == "":
        return "--"
    return str(value)


def _level(value: Any) -> str:
    try:
        if value is None or value == "":
            return "--"
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "--"
