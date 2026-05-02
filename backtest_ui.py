"""
回测验证 Streamlit 页面
"""
import streamlit as st
import pandas as pd
from datetime import datetime

from config import (
    BACKTEST_EVAL_WINDOW, BACKTEST_STOP_LOSS, BACKTEST_TAKE_PROFIT,
    BACKTEST_NEUTRAL_BAND,
)


def backtest_page():
    """回测验证页面"""
    st.header("回测验证")
    st.caption("验证历史信号在后续窗口中的实际表现，评估交易信号的准确性")

    # ---- 控制区 ----
    col1, col2, col3 = st.columns(3)
    with col1:
        symbol = st.text_input("股票代码", value="000001", help="A股输入6位数字")
    with col2:
        market = st.selectbox("市场", options=["CN", "HK", "US"], key="bt_market")
    with col3:
        period = st.selectbox("数据周期", options=["1y", "2y", "5y"],
                               index=1, help="建议2年以上以保证样本量")

    # ---- 参数 ----
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

    # ---- 运行 ----
    if st.button("开始回测", type="primary", use_container_width=True):
        with st.spinner(f"正在回测 {symbol}，可能需要 5-30 秒..."):
            from backtest_adapter import BacktestAdapter
            adapter = BacktestAdapter()
            output = adapter.run(
                symbol=symbol.strip(),
                market=market,
                period=period,
                eval_window_days=int(eval_window),
                stop_loss_pct=stop_loss,
                take_profit_pct=take_profit,
                neutral_band_pct=neutral_band,
            )

        summary = output["summary"]
        results = output["results"]
        completed = [r for r in results if r.get("eval_status") == "completed"]

        if "error" in summary:
            st.error(f"回测失败: {summary['error']}")
            return

        if not completed:
            st.warning("没有足够的有效回测结果。请尝试更长的数据周期或更大的评估窗口。")
            return

        # ---- 概览指标 ----
        st.subheader("回测概览")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("总信号数", summary["total_evaluations"])
        m2.metric("做多信号", summary["long_count"])
        m3.metric("做空/观望", summary["cash_count"])
        m4.metric(f"方向准确率", f"{summary['direction_accuracy_pct']}%"
                  if summary['direction_accuracy_pct'] else "N/A")
        m5.metric(f"胜率", f"{summary['win_rate_pct']}%"
                  if summary['win_rate_pct'] else "N/A")

        m6, m7, m8, m9, m10 = st.columns(5)
        m6.metric("赢/输/平", f"{summary['win_count']}/{summary['loss_count']}/{summary['neutral_count']}")
        m7.metric("平均持仓收益", f"{summary['avg_stock_return_pct']}%"
                  if summary['avg_stock_return_pct'] else "N/A")
        m8.metric("平均模拟收益", f"{summary['avg_simulated_return_pct']}%"
                  if summary['avg_simulated_return_pct'] else "N/A")
        m9.metric(f"止损触发率", f"{summary['stop_loss_trigger_rate']}%"
                  if summary['stop_loss_trigger_rate'] else "N/A")
        m10.metric(f"止盈触发率", f"{summary['take_profit_trigger_rate']}%"
                   if summary['take_profit_trigger_rate'] else "N/A")

        # ---- 信号分类 ----
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
            st.dataframe(pd.DataFrame(bd_rows), use_container_width=True, hide_index=True)

        # ---- 明细表 ----
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
        st.dataframe(pd.DataFrame(detail_rows), use_container_width=True, hide_index=True)

        # ---- 保存 ----
        if st.button("保存结果"):
            path = adapter.save_results(symbol.strip(), market, output)
            st.success(f"已保存: {path}")
