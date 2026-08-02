"""Unified trading workbench for account, risk, audit, scheduler, and broker state."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from broker_execution import build_broker_adapter
from deployment_readiness import DeploymentReadinessService
from paper_trading import PaperTradingService
from ui.scheduler_status import load_scheduler_status, render_scheduler_status


def _money(value) -> str:
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "--"


def _pct(value) -> str:
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "--"


def _render_account_overview(summary: dict) -> None:
    risk = summary.get("risk") or {}
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("账户权益", _money(summary.get("equity")))
    col2.metric("可用现金", _money(summary.get("cash")))
    col3.metric("累计收益", _pct(summary.get("total_return_pct")))
    col4.metric("组合回撤", _pct(risk.get("drawdown_pct")))
    col5.metric("持仓/待成交", f"{summary.get('open_positions', 0)} / {summary.get('pending_orders', 0)}")
    col6.metric("开放告警", len(summary.get("open_alerts") or []))

    audit = summary.get("audit") or {}
    reconciliation = summary.get("last_reconciliation") or {}
    if risk.get("block_new_entries"):
        reasons = risk.get("automatic_breaches") or [risk.get("manual_halt_reason") or "人工停机"]
        st.error("新开仓已被强制阻断：" + "；".join(str(item) for item in reasons if item))
    elif audit.get("valid") and reconciliation.get("status") in {None, "ok"}:
        st.success("账户可继续模拟执行：审计链有效，最近日终对账无差异。")
    else:
        st.warning(
            f"账户完整性待确认：审计链 {'通过' if audit.get('valid') else '失败'}，"
            f"最近对账 {reconciliation.get('status') or '尚未执行'}。"
        )


def _render_strategy_control(summary: dict) -> None:
    control = summary.get("strategy_control") or {}
    metrics = control.get("last_metrics") or {}
    status_labels = {
        "observing": "观察中",
        "active": "继续运行",
        "cash": "保持现金",
    }
    st.markdown("#### 实验策略控制")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("状态", status_labels.get(control.get("status"), control.get("status") or "--"))
    col2.metric("活动规则", control.get("active_rule_id") or "--")
    col3.metric(
        "已结算样本",
        f"{metrics.get('settled_trades', 0)} / 30",
    )
    col4.metric("扣费净盈亏", _money(metrics.get("net_pnl")))
    profit_factor = metrics.get("profit_factor")
    col5.metric(
        "利润因子",
        f"{float(profit_factor):.2f}" if profit_factor is not None else "--",
    )
    st.caption(
        f"规则版本：{control.get('active_strategy_version') or '--'}。"
        "少于30笔只观察；达到30笔后若扣费累计收益不为正或利润因子低于1，"
        "只切换到通过五年训练、样本外、费用、超额收益和回撤门槛的不可变候选；"
        "没有合格候选则保持现金。"
    )
    if control.get("reason"):
        if control.get("status") == "cash":
            st.warning(control["reason"])
        else:
            st.info(control["reason"])
    performance = summary.get("strategy_performance") or []
    if performance:
        st.dataframe(
            pd.DataFrame(performance),
            width="stretch",
            hide_index=True,
        )


def _render_positions_and_orders(summary: dict) -> None:
    positions = summary.get("positions") or []
    st.markdown("#### 当前持仓")
    if positions:
        st.dataframe(
            pd.DataFrame([
                {
                    "代码": row.get("symbol"),
                    "名称": row.get("name"),
                    "策略": row.get("strategy"),
                    "规则": row.get("strategy_rule_id"),
                    "版本": row.get("strategy_version"),
                    "行业": row.get("industry"),
                    "数量": row.get("quantity"),
                    "可卖": row.get("available_quantity"),
                    "买入日": row.get("buy_date"),
                    "成本价": row.get("average_price"),
                    "标记价": row.get("mark_price"),
                    "未实现盈亏": row.get("unrealized_pnl"),
                    "止损": row.get("stop_loss"),
                    "止盈": row.get("take_profit_1"),
                }
                for row in positions
            ]),
            width="stretch",
            hide_index=True,
        )
    else:
        st.caption("当前空仓。")

    st.markdown("#### 最近订单")
    orders = summary.get("orders") or []
    if orders:
        st.dataframe(
            pd.DataFrame([
                {
                    "日期": row.get("trade_date") or row.get("scheduled_date"),
                    "订单号": row.get("order_id"),
                    "策略": row.get("strategy"),
                    "规则": row.get("strategy_rule_id"),
                    "代码": row.get("symbol"),
                    "方向": row.get("side"),
                    "状态": row.get("status"),
                    "数量": row.get("quantity"),
                    "成交价": row.get("filled_price"),
                    "费用": row.get("fee"),
                    "原因": row.get("reason"),
                }
                for row in orders[:100]
            ]),
            width="stretch",
            hide_index=True,
        )
    else:
        st.caption("暂无订单。")


def _render_risk_controls(service: PaperTradingService, summary: dict) -> None:
    risk = summary.get("risk") or {}
    limits = risk.get("limits") or {}
    st.markdown("#### 硬风控状态")
    st.dataframe(
        pd.DataFrame([
            {"规则": "组合最大回撤", "阈值": f"{limits.get('max_drawdown_pct', '--')}%", "当前": _pct(risk.get("drawdown_pct"))},
            {"规则": "组合单日亏损", "阈值": f"{limits.get('max_daily_loss_pct', '--')}%", "当前": _pct(risk.get("daily_return_pct"))},
            {"规则": "行业集中度", "阈值": f"{limits.get('max_industry_exposure_pct', '--')}%", "当前": "逐笔入场检查"},
            {"规则": "成交容量", "阈值": f"{limits.get('max_order_participation_pct', '--')}%", "当前": "逐笔入场检查"},
            {"规则": "行情陈旧", "阈值": f"{limits.get('max_data_age_days', '--')}天", "当前": "逐笔入场检查"},
        ]),
        width="stretch",
        hide_index=True,
    )

    with st.form("trading_emergency_halt_form", clear_on_submit=False):
        target_halt = st.toggle(
            "紧急停机",
            value=bool(risk.get("manual_halt")),
            help="开启后立即撤销所有待成交订单并禁止新开仓；不会自动卖出已有持仓。",
        )
        halt_reason = st.text_input(
            "操作原因",
            value=str(risk.get("manual_halt_reason") or ""),
            placeholder="例如：数据源异常、人工复核",
        )
        apply_halt = st.form_submit_button("应用风控状态", type="primary")
    if apply_halt:
        if target_halt and len(halt_reason.strip()) < 4:
            st.warning("开启紧急停机时必须填写明确原因。")
        else:
            service.set_emergency_halt(
                enabled=target_halt,
                reason=halt_reason.strip() or "人工解除停机",
            )
            st.rerun()

    with st.form("trading_cancel_pending_form", clear_on_submit=False):
        confirm_cancel = st.checkbox("确认撤销当前全部待成交订单")
        cancel_reason = st.text_input("撤销原因", placeholder="例如：计划作废")
        cancel_orders = st.form_submit_button("撤销待成交订单")
    if cancel_orders:
        if not confirm_cancel or len(cancel_reason.strip()) < 4:
            st.warning("请勾选确认并填写明确撤销原因。")
        else:
            service.cancel_pending_orders(reason=cancel_reason.strip())
            st.rerun()

    alerts = summary.get("open_alerts") or []
    st.markdown("#### 开放告警")
    if not alerts:
        st.caption("当前没有开放告警。")
        return
    st.dataframe(pd.DataFrame(alerts), width="stretch", hide_index=True)
    alert_options = {
        f"{row.get('code')} · {row.get('message')}": row.get("alert_id")
        for row in alerts
        if row.get("alert_id")
    }
    with st.form("trading_alert_ack_form", clear_on_submit=False):
        selected = st.selectbox("选择告警", options=list(alert_options))
        note = st.text_input("处理说明", placeholder="说明已核对的内容")
        acknowledge = st.form_submit_button("确认已处理")
    if acknowledge and selected:
        service.acknowledge_alert(alert_options[selected], note=note.strip())
        st.rerun()


def _render_audit(summary: dict) -> None:
    audit = summary.get("audit") or {}
    reconciliation = summary.get("last_reconciliation") or {}
    corporate_action_sync = (
        reconciliation.get("corporate_actions")
        or summary.get("last_corporate_action_sync")
        or {}
    )
    col1, col2, col3 = st.columns(3)
    col1.metric("审计事件", audit.get("events", 0))
    col2.metric("审计链", "通过" if audit.get("valid") else "失败")
    col3.metric("现金对账差额", _money(reconciliation.get("cash_difference")))
    if reconciliation:
        st.dataframe(
            pd.DataFrame([
                {
                    "结算日": reconciliation.get("as_of_date"),
                    "状态": reconciliation.get("status"),
                    "现金账面": reconciliation.get("recorded_cash"),
                    "现金重算": reconciliation.get("expected_cash"),
                    "差额": reconciliation.get("cash_difference"),
                    "订单": reconciliation.get("orders"),
                    "成交": reconciliation.get("fills"),
                    "持仓": reconciliation.get("positions"),
                    "公司行为数据": corporate_action_sync.get("status"),
                    "公司行为入账": corporate_action_sync.get("applied"),
                    "错误": "；".join(reconciliation.get("errors") or []),
                }
            ]),
            width="stretch",
            hide_index=True,
        )
    corporate_actions = summary.get("corporate_actions") or []
    if corporate_actions:
        st.markdown("#### 公司行为流水")
        st.dataframe(
            pd.DataFrame(corporate_actions[:100]),
            width="stretch",
            hide_index=True,
        )
    if corporate_action_sync.get("errors"):
        st.warning(
            "公司行为数据不完整："
            + "；".join(str(item) for item in corporate_action_sync["errors"][:5])
        )
    events = summary.get("recent_audit_events") or []
    if events:
        st.markdown("#### 最近审计流水")
        st.dataframe(
            pd.DataFrame([
                {
                    "序号": row.get("sequence"),
                    "时间": row.get("occurred_at"),
                    "事件": row.get("event_type"),
                    "前序哈希": str(row.get("previous_hash") or "")[:12],
                    "事件哈希": str(row.get("event_hash") or "")[:12],
                }
                for row in events[:100]
            ]),
            width="stretch",
            hide_index=True,
        )


def _render_broker() -> None:
    adapter = build_broker_adapter()
    readiness = adapter.readiness()
    st.markdown("#### 券商接入状态")
    col1, col2, col3 = st.columns(3)
    col1.metric("交易模式", readiness.get("mode") or "--")
    col2.metric("连接条件", "就绪" if readiness.get("ready") else "未就绪")
    col3.metric("真实委托", "已解锁" if readiness.get("live_order_enabled") else "硬阻断")
    st.info(readiness.get("message") or "--")
    checks = readiness.get("checks") or {}
    st.dataframe(
        pd.DataFrame([
            {"检查项": key, "结果": "通过" if passed else "未通过"}
            for key, passed in checks.items()
        ]),
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "QMT/MiniQMT 真实委托需要 Windows 客户端、xtquant、账户目录、账号、"
        "qmt_live 模式、总开关和确认短语全部满足。默认只能模拟或只读查询。"
    )
    if readiness.get("ready") and readiness.get("mode") != "paper":
        if st.button("读取券商账户快照"):
            snapshot = adapter.query_snapshot()
            st.session_state["broker_account_snapshot"] = snapshot
    snapshot = st.session_state.get("broker_account_snapshot")
    if isinstance(snapshot, dict):
        if snapshot.get("status") == "ok":
            st.json(snapshot, expanded=False)
        else:
            st.warning(snapshot.get("message") or "券商账户查询失败")


def _render_launch_readiness(summary: dict) -> None:
    report = DeploymentReadinessService().evaluate(paper_summary=summary)
    st.markdown("#### 上线门禁")
    if report.get("status") == "ready":
        st.success("研究、组合回测、模拟盘和小资金实盘门禁均已通过。")
    else:
        st.warning(f"当前停留在「{report.get('current_stage')}」：{report.get('message')}")
    st.dataframe(
        pd.DataFrame([
            {
                "顺序": row.get("order"),
                "阶段": row.get("name"),
                "状态": "通过" if row.get("status") == "passed" else "阻断",
                "原因": row.get("reason"),
            }
            for row in report.get("stages") or []
        ]),
        width="stretch",
        hide_index=True,
    )
    st.caption("任何阶段都不会自动转正、自动接入真实委托或自动扩仓。")


def render_trading_workbench_page() -> None:
    """Render the full local trading operations workspace."""
    st.markdown("# 交易工作台")
    st.caption("统一查看模拟账户、组合风控、订单成交、审计对账、调度状态和券商接入闸门。")

    service = PaperTradingService()
    summary = service.get_summary()
    _render_account_overview(summary)
    _render_strategy_control(summary)

    account_tab, risk_tab, audit_tab, broker_tab, schedule_tab, launch_tab = st.tabs(
        ["持仓与订单", "风控与告警", "审计与对账", "券商接入", "自动调度", "上线门禁"]
    )
    with account_tab:
        _render_positions_and_orders(summary)
    with risk_tab:
        _render_risk_controls(service, summary)
    with audit_tab:
        _render_audit(summary)
    with broker_tab:
        _render_broker()
    with schedule_tab:
        status = load_scheduler_status()
        render_scheduler_status(status)
        if not status:
            st.caption("暂无调度状态文件，不能仅凭配置判断任务是否运行。")
    with launch_tab:
        _render_launch_readiness(summary)
