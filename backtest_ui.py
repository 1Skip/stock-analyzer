"""
回测验证 Streamlit 页面
"""
import html

import streamlit as st
import pandas as pd
from ui.loading import status_loading
from ui.cached_data import quote_service, resolve_cached_stock_input
from quality_monitor import build_backtest_risk_summary

from config import (
    BACKTEST_EVAL_WINDOW, BACKTEST_STOP_LOSS, BACKTEST_TAKE_PROFIT,
    BACKTEST_NEUTRAL_BAND,
)


def _resolve_backtest_target(query: str, market: str) -> tuple[str, str]:
    """把回测输入解析为股票代码和名称。"""
    query = str(query or "").strip()
    if not query:
        return "", ""
    if market == "CN":
        match = resolve_cached_stock_input(query, market)
        if match:
            return match[0], match[1]
        if query.isdigit() and len(query) == 6:
            return query, quote_service.get_stock_name(query, market) or query
        return query, query
    symbol = query.upper()
    return symbol, quote_service.get_stock_name(symbol, market) or symbol


def _render_backtest_target_header(symbol: str, stock_name: str, market: str, *, status: str | None = None) -> None:
    """展示回测标的标题栏，错误/状态不混入股票名称。"""
    display_name = stock_name if stock_name and stock_name != symbol else ""
    subtitle = html.escape(market)
    if status:
        subtitle += f" · {html.escape(status)}"
    st.markdown(
        f"""
        <div style="margin:12px 0 16px;padding:14px 16px;border-radius:14px;
                    border:1px solid rgba(128,128,128,0.18);
                    background:linear-gradient(135deg,rgba(0,122,255,0.08),rgba(128,128,128,0.04));">
          <div style="font-size:0.82rem;opacity:0.65;margin-bottom:4px;">回测标的</div>
          <div style="font-size:1.28rem;font-weight:700;line-height:1.3;">
            {html.escape(symbol)}{f" · {html.escape(display_name)}" if display_name else ""}
          </div>
          <div style="font-size:0.85rem;opacity:0.65;margin-top:4px;">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _clear_backtest_result() -> None:
    """清理旧回测结果，避免新输入时显示上一次标的。"""
    st.session_state.pop("backtest_result", None)


def _backtest_target_matches_input(result, symbol_input, market, period, eval_window) -> bool:
    """判断当前输入是否仍对应已缓存回测结果。"""
    if not result or result.get("error"):
        return False
    query = str(symbol_input or "").strip()
    result_symbol = str(result.get("symbol") or "")
    result_name = str(result.get("stock_name") or "")
    input_matches = query in {result_symbol, result_name}
    return (
        input_matches
        and market == result.get("market")
        and period == result.get("period")
        and int(eval_window) == int(result.get("eval_window", -1))
    )


def _run_backtest_task(symbol_input, market, period, eval_window, stop_loss, take_profit, neutral_band):
    """后台执行回测。"""
    symbol, stock_name = _resolve_backtest_target(symbol_input, market)
    if not symbol:
        return {"error": "请输入股票代码或名称"}

    from backtest_adapter import BacktestAdapter

    adapter = BacktestAdapter()
    output = adapter.run(
        symbol=symbol,
        market=market,
        period=period,
        eval_window_days=int(eval_window),
        stop_loss_pct=stop_loss,
        take_profit_pct=take_profit,
        neutral_band_pct=neutral_band,
    )
    return {
        "symbol": symbol,
        "stock_name": stock_name,
        "market": market,
        "period": period,
        "eval_window": int(eval_window),
        "output": output,
    }


def _render_backtest_result(result):
    if result.get("error"):
        st.error(result["error"])
        return

    symbol = result["symbol"]
    stock_name = result["stock_name"]
    market = result["market"]
    period = result["period"]
    eval_window = result["eval_window"]
    output = result["output"]
    summary = output["summary"]
    results = output["results"]
    completed = [r for r in results if r.get("eval_status") == "completed"]

    if "error" in summary:
        _render_backtest_target_header(symbol, stock_name, market, status="回测失败")
        st.error(f"回测失败: {summary['error']}")
        return

    if not completed:
        _render_backtest_target_header(symbol, stock_name, market, status="无有效结果")
        st.warning("没有足够的有效回测结果。请尝试更长的数据周期或更大的评估窗口。")
        return

    _render_backtest_target_header(symbol, stock_name, market, status=f"{period} · 评估窗口 {eval_window} 天")

    st.subheader("回测概览")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("总信号数", summary["total_evaluations"])
    m2.metric("做多信号", summary["long_count"])
    m3.metric("做空/观望", summary["cash_count"])
    m4.metric(f"方向准确率", f"{summary['direction_accuracy_pct']}%" if summary['direction_accuracy_pct'] else "N/A")
    m5.metric(f"胜率", f"{summary['win_rate_pct']}%" if summary['win_rate_pct'] else "N/A")

    m6, m7, m8, m9, m10 = st.columns(5)
    m6.metric("赢/输/平", f"{summary['win_count']}/{summary['loss_count']}/{summary['neutral_count']}")
    m7.metric("平均持仓收益", f"{summary['avg_stock_return_pct']}%" if summary['avg_stock_return_pct'] else "N/A")
    m8.metric("平均模拟收益", f"{summary['avg_simulated_return_pct']}%" if summary['avg_simulated_return_pct'] else "N/A")
    m9.metric(f"止损触发率", f"{summary['stop_loss_trigger_rate']}%" if summary['stop_loss_trigger_rate'] else "N/A")
    m10.metric(f"止盈触发率", f"{summary['take_profit_trigger_rate']}%" if summary['take_profit_trigger_rate'] else "N/A")

    bench_ret = summary.get("benchmark_return_pct")
    excess_ret = summary.get("excess_return_pct")
    m11, m12, _, _, _ = st.columns(5)
    m11.metric("同期大盘", f"{bench_ret:+.2f}%" if bench_ret is not None else "N/A", delta=None)
    m12.metric(
        "超额收益",
        f"{excess_ret:+.2f}%" if excess_ret is not None else "N/A",
        delta=f"{excess_ret:+.2f}%" if excess_ret is not None else None,
        delta_color="normal",
    )

    risk_summary = build_backtest_risk_summary(results)
    with st.expander("收益分布 / 失败样本", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("最优模拟收益", _fmt_pct(risk_summary.get("best_simulated_return_pct")))
        c2.metric("最差模拟收益", _fmt_pct(risk_summary.get("worst_simulated_return_pct")))
        c3.metric("亏损样本", risk_summary.get("loss_count", 0))
        c4.metric("完成样本", risk_summary.get("completed", 0))
        worst_cases = risk_summary.get("worst_cases") or []
        if worst_cases:
            st.dataframe(
                pd.DataFrame([
                    {
                        "日期": item.get("analysis_date"),
                        "信号": item.get("signal"),
                        "模拟收益(%)": item.get("simulated_return_pct"),
                        "结果": item.get("outcome"),
                        "触发": item.get("first_hit"),
                        "出场原因": item.get("simulated_exit_reason"),
                    }
                    for item in worst_cases
                ]),
                width="stretch",
                hide_index=True,
            )

    st.subheader("信号分类统计")
    breakdown = summary.get("signal_breakdown", {})
    if breakdown:
        bd_rows = []
        for sig, stats in breakdown.items():
            bd_rows.append({
                "信号": sig,
                "总数": stats["total"],
                "胜": stats["win"],
                "负": stats["loss"],
                "平": stats["neutral"],
                "胜率(%)": stats["win_rate_pct"],
            })
        st.dataframe(pd.DataFrame(bd_rows), width="stretch", hide_index=True)

    st.subheader("回测明细")
    detail_rows = []
    for r in completed:
        detail_rows.append({
            "日期": r.get("analysis_date"),
            "信号": r.get("signal"),
            "入场价": r.get("start_price"),
            "出场价": r.get("simulated_exit_price"),
            "持仓收益(%)": r.get("stock_return_pct"),
            "模拟收益(%)": r.get("simulated_return_pct"),
            "结果": r.get("outcome"),
            "方向正确": "✅" if r.get("direction_correct") else ("❌" if r.get("direction_correct") is False else "—"),
            "触发": r.get("first_hit", ""),
            "出场原因": r.get("simulated_exit_reason", ""),
        })
    st.dataframe(pd.DataFrame(detail_rows), width="stretch", hide_index=True)

    if st.button("保存结果"):
        from backtest_adapter import BacktestAdapter
        path = BacktestAdapter().save_results(symbol, market, output)
        st.success(f"已保存: {path}")


def _fmt_pct(value):
    return f"{value:+.2f}%" if isinstance(value, (int, float)) else "N/A"


def backtest_page():
    """回测验证页面"""
    st.header("回测验证")
    st.caption("验证历史信号在后续窗口中的实际表现，评估交易信号的准确性")

    # ---- 控制区 ----
    MARKET_MAP = {"A股": "CN", "港股": "HK", "美股": "US"}
    PERIOD_OPTIONS = {"6个月 · 快速验证": "6mo", "1年 · 标准回测": "1y",
                      "2年 · 深度验证": "2y", "5年 · 长期验证": "5y"}

    if "bt_symbol_input" not in st.session_state:
        st.session_state.bt_symbol_input = "000001"

    with st.form("backtest_form", clear_on_submit=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            symbol_input = st.text_input(
                "股票代码或名称",
                help="A股可输入6位代码或股票名称",
                key="bt_symbol_input",
            )
        with col2:
            market_label = st.selectbox("市场", options=list(MARKET_MAP.keys()),
                                        index=0, key="bt_market_label")
            market = MARKET_MAP[market_label]
        with col3:
            period_label = st.selectbox("数据周期", options=list(PERIOD_OPTIONS.keys()),
                                        index=1, help="6个月起可用，建议1年以上",
                                        key="bt_period_label")
            period = PERIOD_OPTIONS[period_label]

        with st.expander("回测参数", expanded=False):
            pc1, pc2, pc3, pc4 = st.columns(4)
            with pc1:
                eval_window = st.number_input("评估窗口（天）", min_value=5, max_value=60,
                                              value=BACKTEST_EVAL_WINDOW)
            with pc2:
                stop_loss = st.number_input("止损线（%）", min_value=-20.0, max_value=0.0,
                                            value=BACKTEST_STOP_LOSS, step=0.5)
            with pc3:
                take_profit = st.number_input("止盈线（%）", min_value=0.0, max_value=50.0,
                                              value=BACKTEST_TAKE_PROFIT, step=0.5)
            with pc4:
                neutral_band = st.number_input("中性区间（%）", min_value=0.5, max_value=10.0,
                                               value=BACKTEST_NEUTRAL_BAND, step=0.5)

        submitted = st.form_submit_button("开始回测", type="primary", width="stretch")

    if submitted:
        _clear_backtest_result()
        with status_loading(f"\u6b63\u5728\u56de\u6d4b {symbol_input}\uff0c\u53ef\u80fd\u9700\u8981 5-30 \u79d2...", 20):
            st.session_state.backtest_result = _run_backtest_task(
                symbol_input,
                market,
                period,
                eval_window,
                stop_loss,
                take_profit,
                neutral_band,
            )

    current_result = st.session_state.get("backtest_result")
    if (
        current_result
        and _backtest_target_matches_input(current_result, symbol_input, market, period, eval_window)
    ):
        _render_backtest_result(st.session_state.backtest_result)
    elif current_result:
        st.caption("当前输入与上一次回测结果不一致，点击「开始回测」生成新结果。")
