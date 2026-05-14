"""个股分析页面 — 输入表单 + 数据获取 + 结果渲染"""
import html
import concurrent.futures
import streamlit as st
import pandas as pd
import numpy as np
from chart_utils import classify_signal
from config import (
    RSI_OVERBOUGHT, RSI_OVERSOLD, KDJ_OVERBOUGHT, KDJ_OVERSOLD,
    DEFAULT_COLOR_SCHEME, COLOR_SCHEMES, AI_ENABLED,
)
from technical_indicators import TechnicalIndicators
from watchlist import add_to_watchlist, remove_from_watchlist, is_in_watchlist
from ui.cached_data import (
    get_cached_stock_data, get_cached_stock_info,
    get_cached_realtime_quote, get_cached_intraday_data,
    get_cached_stock_profile, get_cached_stock_extended_info,
    resolve_cached_stock_input, get_cached_benchmark_data,
)
from ui.charts import (
    latest_indicator_values,
    plot_candlestick_chart, plot_macd_chart, plot_rsi_chart, plot_kdj_chart,
    plot_boll_chart, plot_intraday_chart,
)
from ui.ai_analysis_ui import display_ai_analysis_card
from ui.decision_dashboard import render_decision_dashboard
from ui.stock_search import suggest_stock_inputs


def _validate_symbol(sym, mkt):
    """校验股票代码格式，返回(valid, error_msg)"""
    sym = sym.strip()
    if not sym:
        return False, "请输入股票代码"
    if mkt == "CN":
        if not sym.isdigit() or len(sym) != 6:
            return False, "A股代码应为6位数字，如: 000001, 600519"
    elif mkt == "US":
        if not sym.isascii() or not sym.replace('.', '').replace('-', '').isalpha() or len(sym) > 10:
            return False, "美股代码应为纯字母，如: AAPL, TSLA, BRK.B"
    elif mkt == "HK":
        if not sym.isdigit() or len(sym) < 1 or len(sym) > 5:
            return False, "港股代码应为1-5位数字，如: 00700, 9988"
    return True, ""


def _format_val(row, col, precision):
    """安全格式化指标值"""
    val = row.get(col)
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return '--'
    return f'{float(val):.{precision}f}'


def _format_large_number(value):
    """把股本/市值格式化为中文单位。"""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "--"
    value = float(value)
    abs_value = abs(value)
    if abs_value >= 1e8:
        return f"{value / 1e8:.2f}亿"
    if abs_value >= 1e4:
        return f"{value / 1e4:.2f}万"
    return f"{value:.2f}"


def _format_optional_number(value, suffix="", precision=2):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "--"
    return f"{float(value):.{precision}f}{suffix}"


def _format_money(value):
    return _format_large_number(value)


def _latest_news_date(news):
    """返回新闻列表中的最新可见日期。"""
    candidates = []
    for item in news or []:
        date_text = str(item.get("date") or item.get("publish_time") or "").strip()
        if date_text:
            parsed = pd.to_datetime(date_text, errors="coerce")
            candidates.append((parsed, date_text))
    parsed_candidates = [candidate for candidate in candidates if pd.notna(candidate[0])]
    if parsed_candidates:
        return max(parsed_candidates, key=lambda candidate: candidate[0])[1]
    if candidates:
        return candidates[0][1]
    return "--"


def _build_short_history_notice(symbol, stock_name, data_len, period):
    """生成短历史数据提示。"""
    if data_len >= 30:
        return None

    display_name = stock_name if stock_name and stock_name != symbol else symbol
    if data_len < 20:
        return (
            f"{symbol} {display_name} 可用历史数据较少（仅{data_len}个交易日），"
            "可能是新股/次新股或数据源只返回上市后行情。长周期指标（如 MA20/MA60、RSI24、BOLL）"
            "暂不完整，建议优先参考分时图、价格走势和短线指标。"
        )

    return (
        f"{symbol} {display_name} 历史数据偏少（{data_len}个交易日），"
        f"当前选择「{period}」周期时，部分长周期指标可能不完整。"
    )


def _render_stock_profile(profile):
    """渲染基础资料/估值卡片。"""
    profile = profile or {"loading": True}

    with st.expander("基础资料 / 估值", expanded=False):
        if profile.get("loading"):
            st.caption("基础资料仍在加载或当前请求未及时返回；请稍等几秒后刷新/重新查询即可读取缓存。")

        col_industry, col_listing, col_market_cap, col_float_cap = st.columns(4)
        with col_industry:
            st.metric("行业", profile.get("industry") or "--")
        with col_listing:
            st.metric("上市日期", profile.get("listing_date") or "--")
        with col_market_cap:
            st.metric("总市值", _format_large_number(profile.get("market_cap")))
        with col_float_cap:
            st.metric("流通市值", _format_large_number(profile.get("float_market_cap")))

        col_total, col_float, col_pe, col_pb = st.columns(4)
        with col_total:
            st.metric("总股本", _format_large_number(profile.get("total_shares")))
        with col_float:
            st.metric("流通股", _format_large_number(profile.get("float_shares")))
        with col_pe:
            st.metric("PE(TTM)", _format_optional_number(profile.get("pe_ttm")))
        with col_pb:
            st.metric("PB", _format_optional_number(profile.get("pb")))

        turnover_rate = profile.get("turnover_rate")
        if turnover_rate is not None:
            st.caption(f"换手率：{_format_optional_number(turnover_rate, '%')}")

        if profile.get("source") or profile.get("updated_at"):
            st.caption(f"来源：{profile.get('source') or '未知'} · 更新：{profile.get('updated_at') or '--'}")


def _render_extended_info(extended_info):
    """渲染财务摘要/资金流/新闻信息。"""
    extended_info = extended_info or {"loading": True}
    financial = extended_info.get("financial") or {}
    fund_flow = extended_info.get("fund_flow") or {}
    news = extended_info.get("news") or []

    with st.expander("财务 / 资金 / 新闻", expanded=False):
        if extended_info.get("loading"):
            st.caption("扩展信息仍在加载或当前请求未及时返回；请稍等几秒后刷新/重新查询即可读取缓存。")

        metrics = financial.get("metrics") or {}
        if metrics:
            st.caption(f"财务报告期：{financial.get('period') or '--'}")
            col_revenue, col_profit, col_cash = st.columns(3)
            with col_revenue:
                st.metric("营业总收入", _format_money(metrics.get("营业总收入")))
            with col_profit:
                st.metric("归母净利润", _format_money(metrics.get("归母净利润")))
            with col_cash:
                st.metric("经营现金流", _format_money(metrics.get("经营现金流量净额")))
        else:
            st.caption("财务报告期：暂无")

        if fund_flow:
            st.caption(f"资金流日期：{fund_flow.get('date') or '--'}")
            col_main, col_ratio, col_five = st.columns(3)
            with col_main:
                st.metric("主力净流入", _format_money(fund_flow.get("main_net_inflow")))
            with col_ratio:
                st.metric("主力净占比", _format_optional_number(fund_flow.get("main_net_inflow_ratio"), "%"))
            with col_five:
                st.metric("近5日主力净流入", _format_money(fund_flow.get("five_day_main_net_inflow")))
        else:
            st.caption("资金流日期：暂无")

        news_date = _latest_news_date(news)
        if news:
            st.caption(f"新闻最新：{news_date}")
        else:
            st.caption("新闻最新：暂无（当前数据源未返回该股相关新闻）")

        if news:
            st.caption("相关新闻：")
            for item in news[:5]:
                title = html.escape(str(item.get("title", "")))
                date = html.escape(str(item.get("date", "")))
                url = str(item.get("url", ""))
                if url.startswith("http"):
                    st.markdown(f"- [{title}]({url}) <span style='opacity:0.6'>{date}</span>", unsafe_allow_html=True)
                else:
                    st.markdown(f"- {title} <span style='opacity:0.6'>{date}</span>", unsafe_allow_html=True)

        if extended_info.get("source") or extended_info.get("updated_at"):
            st.caption(f"来源：{extended_info.get('source') or '未知'} · 更新：{extended_info.get('updated_at') or '--'}")


def _render_market_news(extended_info):
    """渲染市场快讯/催化消息。"""
    if not extended_info:
        return

    market_news = extended_info.get("market_news") or []
    if not market_news:
        return

    with st.expander("市场快讯 / 催化消息", expanded=False):
        st.caption("用于辅助判断市场情绪、政策/海外/宏观催化；不直接替代个股新闻。")
        for item in market_news[:8]:
            title = html.escape(str(item.get("title") or item.get("summary") or ""))
            tag = html.escape(str(item.get("tag") or item.get("source") or "市场动态"))
            date = html.escape(str(item.get("date") or ""))
            url = str(item.get("url") or "")
            meta = " · ".join(part for part in [tag, date] if part)
            suffix = f" <span style='opacity:0.6'>{meta}</span>" if meta else ""
            if url.startswith("http"):
                st.markdown(f"- [{title}]({url}){suffix}", unsafe_allow_html=True)
            else:
                st.markdown(f"- {title}{suffix}", unsafe_allow_html=True)


def _render_inline_note(message):
    """渲染与上方仪表盘保持距离的轻提示。"""
    st.markdown(
        f'<div class="analysis-inline-note">{html.escape(message)}</div>',
        unsafe_allow_html=True,
    )


def _render_chart_header(title, values=None):
    """渲染统一的图表标题与右侧实时值标签。"""
    chips = "".join(
        f'<span class="chart-value-chip"><b>{html.escape(str(label))}</b> {html.escape(str(value))}</span>'
        for label, value in (values or [])
    )
    st.markdown(
        f'''
        <div class="chart-header-row">
          <p class="chart-section-title">{html.escape(str(title))}</p>
          <div class="chart-value-row">{chips}</div>
        </div>
        ''',
        unsafe_allow_html=True,
    )


def display_signals(signals):
    """显示交易信号 — 4个徽章横排 + 综合建议"""
    if 'error' in signals:
        st.warning(f"{signals['error']}")
        return

    badges_html = ""
    for key, label in [("MACD", "macd"), ("RSI", "rsi"), ("KDJ", "kdj"), ("布林带", "boll")]:
        text = signals.get(label, '--')
        cls = classify_signal(text)
        badges_html += f'<span class="signal-badge {cls}" style="font-size:1rem">{key} · {html.escape(text)}</span>'

    st.markdown(f'<div style="margin:12px 0;font-size:1.05rem">{badges_html}</div>', unsafe_allow_html=True)

    recommendation = signals.get('recommendation', '')
    if recommendation:
        st.markdown(f'<p style="font-size:1.35rem;font-weight:700;margin-top:8px">综合: {html.escape(recommendation)}</p>', unsafe_allow_html=True)


def _display_indicator_values(data):
    """显示技术指标实时数值卡片 — 每条左色条区分，底部留间距"""
    if data is None or data.empty:
        return

    latest = data.iloc[-1]
    rsi_ob = RSI_OVERBOUGHT
    rsi_os = RSI_OVERSOLD
    kdj_ob = KDJ_OVERBOUGHT
    kdj_os = KDJ_OVERSOLD

    card = (
        "background:linear-gradient(135deg,rgba(12,28,43,0.86),rgba(5,13,24,0.72));border-radius:12px;"
        "padding:9px 14px;margin-bottom:7px;"
        "border:1px solid rgba(85,199,255,0.14);box-shadow:0 10px 24px rgba(0,0,0,0.18);"
        "display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:4px 12px;"
    )

    st.markdown('<p class="chart-section-title">技术指标数值</p>', unsafe_allow_html=True)

    # RSI — 红色左边条
    rsi6 = _format_val(latest, 'rsi_6', 2)
    rsi12 = _format_val(latest, 'rsi_12', 2)
    rsi24 = _format_val(latest, 'rsi_24', 2)
    st.markdown(
        f'<div style="{card}border-left:3px solid #ff3b30;">'
        f'<span><b style="margin-right:10px;">RSI</b>'
        f'<span style="color:#ff3b30">6日 {rsi6}</span>  '
        f'<span style="color:#fb8c00">12日 {rsi12}</span>  '
        f'<span style="color:#7b1fa2">24日 {rsi24}</span></span>'
        f'<span style="font-size:0.75rem;color:#9fb0c4;white-space:nowrap;">超买&gt;{rsi_ob} 超卖&lt;{rsi_os}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # KDJ — 蓝色左边条
    k = _format_val(latest, 'kdj_k', 2)
    d = _format_val(latest, 'kdj_d', 2)
    j = _format_val(latest, 'kdj_j', 2)
    st.markdown(
        f'<div style="{card}border-left:3px solid #1e88e5;">'
        f'<span><b style="margin-right:10px;">KDJ</b>'
        f'<span style="color:#1e88e5">K {k}</span>  '
        f'<span style="color:#fb8c00">D {d}</span>  '
        f'<span style="color:#7b1fa2">J {j}</span></span>'
        f'<span style="font-size:0.75rem;color:#9fb0c4;white-space:nowrap;">超买&gt;{kdj_ob} 超卖&lt;{kdj_os}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # MACD — 紫色左边条
    dif = _format_val(latest, 'macd', 2)
    dea = _format_val(latest, 'macd_signal', 2)
    hist = _format_val(latest, 'macd_hist', 2)
    hist_color = '#ff3b30' if (latest.get('macd_hist') or 0) >= 0 else '#34c759'
    st.markdown(
        f'<div style="{card}border-left:3px solid #7b1fa2;">'
        f'<span><b style="margin-right:10px;">MACD</b>'
        f'<span style="color:#42a5f5">DIF {dif}</span>  '
        f'<span style="color:#ff7043">DEA {dea}</span>  '
        f'<span style="color:{hist_color}">柱 {hist}</span></span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # BOLL — 绿色左边条
    upper = _format_val(latest, 'boll_upper', 2)
    mid = _format_val(latest, 'boll_mid', 2)
    lower = _format_val(latest, 'boll_lower', 2)
    price = latest.get('close')
    if price is not None and latest.get('boll_upper') is not None:
        pct_b = (price - latest['boll_lower']) / (latest['boll_upper'] - latest['boll_lower']) * 100
        pct_str = f'%B {pct_b:.0f}%'
    else:
        pct_str = ''
    st.markdown(
        f'<div style="{card}border-left:3px solid #34c759;">'
        f'<span><b style="margin-right:10px;">BOLL</b>'
        f'<span style="color:#ff3b30">上轨 {upper}</span>  '
        f'<span style="color:#1e88e5">中轨 {mid}</span>  '
        f'<span style="color:#34c759">下轨 {lower}</span></span>'
        f'<span style="font-size:0.75rem;color:#9fb0c4;white-space:nowrap;">{pct_str}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # MA 均线 — 灰色左边条
    ma5 = _format_val(latest, 'ma5', 2)
    ma10 = _format_val(latest, 'ma10', 2)
    ma20 = _format_val(latest, 'ma20', 2)
    ma60 = _format_val(latest, 'ma60', 2)
    if ma5 != '--':
        st.markdown(
            f'<div style="{card}border-left:3px solid #8e8e93;">'
            f'<span><b style="margin-right:10px;">均线</b>'
            f'<span>MA5 {ma5}</span>  '
            f'<span>MA10 {ma10}</span>  '
            f'<span>MA20 {ma20}</span>  '
            f'<span>MA60 {ma60}</span></span>'
            f'</div>',
            unsafe_allow_html=True,
        )


def _resolve_watchlist_target(symbol: str, market: str) -> tuple[str, str] | None:
    """尽量把当前输入解析成可加入自选的代码和名称。"""
    symbol = str(symbol or "").strip()
    if not symbol:
        return None
    if market == "CN":
        result = resolve_cached_stock_input(symbol, market)
        if result:
            return result[0], result[1]
        if symbol.isdigit() and len(symbol) == 6:
            return symbol, symbol
        return None
    return symbol, symbol


def _render_watchlist_quick_action(symbol: str, market: str) -> None:
    """在搜索区直接显示加入/移除自选，避免结果加载前看不到入口。"""
    target = _resolve_watchlist_target(symbol, market)
    if not target:
        st.caption("输入或选择股票后，可在这里加入自选。")
        return

    watch_symbol, watch_name = target
    in_watchlist = is_in_watchlist(watch_symbol, market)
    label = "移除自选" if in_watchlist else "加入自选"
    button_type = "secondary" if in_watchlist else "primary"
    if st.button(label, key=f"quick_watchlist_{market}_{watch_symbol}", type=button_type, use_container_width=True):
        if in_watchlist:
            success, msg = remove_from_watchlist(watch_symbol, market)
        else:
            success, msg = add_to_watchlist(watch_symbol, watch_name, market)
        if success:
            st.success(msg)
            st.rerun()
        else:
            st.warning(msg)


def _render_current_stock_header(symbol: str, market: str, period: str, stock_name: str | None = None) -> None:
    """在搜索区下方展示当前待分析标的，避免首屏标题空白。"""
    display_name = stock_name if stock_name and stock_name != symbol else ""
    market_label = {"CN": "A股", "US": "美股", "HK": "港股"}.get(market, market)
    st.markdown(
        f"""
        <div style="margin:8px 0 14px;padding:12px 14px;border-radius:12px;
                    border:1px solid rgba(85,199,255,0.16);
                    background:linear-gradient(135deg,rgba(12,28,43,0.86),rgba(5,13,24,0.72));
                    box-shadow:0 10px 24px rgba(0,0,0,0.16);">
          <div style="font-size:0.78rem;opacity:0.62;margin-bottom:3px;">当前标的</div>
          <div style="font-size:1.05rem;font-weight:700;line-height:1.35;">
            {html.escape(str(symbol or "--"))}{f" · {html.escape(str(display_name))}" if display_name else ""}
          </div>
          <div style="font-size:0.82rem;opacity:0.62;margin-top:3px;">{html.escape(market_label)} · {html.escape(str(period))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_analysis_results(data, signals, quote, symbol, stock_name, market, period, intraday_data=None, profile=None, extended_info=None):
    """渲染个股分析结果 — Apple×Tesla 分层布局"""
    st.markdown('<div id="analysis-results"></div>', unsafe_allow_html=True)
    st.divider()

    # ① 标题行
    col_title, col_watchlist = st.columns([3, 1])
    with col_title:
        display_name = stock_name if stock_name and stock_name != symbol else ""
        market_label = {"CN": "A股", "US": "美股", "HK": "港股"}.get(market, market)
        st.markdown(
            f"""
            <div style="margin:0 0 12px;padding:14px 16px;border-radius:14px;
                        border:1px solid rgba(85,199,255,0.18);
                        background:linear-gradient(135deg,rgba(85,199,255,0.13),rgba(5,13,24,0.78));
                        box-shadow:0 12px 30px rgba(0,0,0,0.20);">
              <div style="font-size:0.82rem;opacity:0.65;margin-bottom:4px;">个股分析标的</div>
              <div style="font-size:1.32rem;font-weight:700;line-height:1.3;">
                {html.escape(symbol)}{f" · {html.escape(display_name)}" if display_name else ""}
              </div>
              <div style="font-size:0.85rem;opacity:0.65;margin-top:4px;">{html.escape(market_label)} · {html.escape(period)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_watchlist:
        if is_in_watchlist(symbol, market):
            if st.button("移除自选", key="remove_watchlist"):
                success, msg = remove_from_watchlist(symbol, market)
                if success:
                    st.success(msg)
                    st.rerun()
        else:
            if st.button("加入自选", key="add_watchlist"):
                success, msg = add_to_watchlist(symbol, stock_name, market)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.warning(msg)


    # ② 核心指标 — 最新价
    last_row = data.iloc[-1] if data is not None and not data.empty else None
    if quote is None and last_row is not None:
        prev_row = data.iloc[-2] if len(data) > 1 else last_row
        change = (last_row['close'] - prev_row['close']) / prev_row['close'] * 100 if prev_row['close'] != 0 else 0
        quote = {
            'price': last_row['close'],
            'high': last_row['high'],
            'low': last_row['low'],
            'open': last_row['open'],
            'volume': int(last_row['volume']),
            'change': change,
        }

    if quote:
        col_price, col_h, col_l, col_v, col_o = st.columns([2, 1, 1, 1, 1])
        with col_price:
            change = quote['change']
            delta_color = "#ff3b30" if change >= 0 else "#34c759"
            delta_sign = "+" if change >= 0 else ""
            st.markdown(f'''
            <div style="background:rgba(26,115,232,0.12);border:1px solid rgba(26,115,232,0.18);
                        border-radius:12px;padding:14px 16px;box-sizing:border-box;">
              <div style="font-size:0.8rem;margin-bottom:6px;font-weight:800;color:inherit;">最新价</div>
              <div style="font-size:2.2rem;font-weight:700;line-height:1.2;">{quote["price"]:.2f}</div>
              <div style="font-size:0.95rem;font-weight:500;color:{delta_color};margin-top:4px;">{delta_sign}{change:.2f}%</div>
            </div>
            ''', unsafe_allow_html=True)
        with col_h:
            st.metric("最高", f"{quote['high']:.2f}")
        with col_l:
            st.metric("最低", f"{quote['low']:.2f}")
        with col_v:
            vol = quote['volume']
            if vol >= 1e8:
                volume = vol / 1e8
                unit = "亿"
            elif vol >= 1e4:
                volume = vol / 1e4
                unit = "万"
            else:
                volume = vol
                unit = ""
            st.metric("成交量", f"{volume:.1f}{unit}")
        with col_o:
            st.metric("今开", f"{quote['open']:.2f}")

    st.write("")

    benchmark_data = None
    if market == "CN":
        benchmark_data = get_cached_benchmark_data("000300", period)
    render_decision_dashboard(data, signals, quote, extended_info, profile, benchmark_data)

    _render_stock_profile(profile)
    if market == "CN":
        _render_extended_info(extended_info)
        _render_market_news(extended_info)

    # ③ 分时图（仅A股）
    if market == "CN":
        if intraday_data is None:
            intraday_data = get_cached_intraday_data(symbol, market)
        if intraday_data is not None and not intraday_data.empty:
            intraday_fig = plot_intraday_chart(intraday_data, quote)
            if intraday_fig:
                st.plotly_chart(intraday_fig, use_container_width=True,
                                config={'displayModeBar': False})
        else:
            now = pd.Timestamp.now()
            weekday = now.dayofweek
            if weekday >= 5:
                _render_inline_note("📌 今日非交易日，暂无分时数据")
            else:
                _render_inline_note("📌 分时数据暂不可用，请稍后刷新")

    # ③ 技术指标实时数值卡片
    _display_indicator_values(data)

    st.divider()

    # ④ 交易信号
    display_signals(signals)

    # ⑤ AI 辅助解读（可选）
    if AI_ENABLED:
        display_ai_analysis_card(data, signals, symbol, stock_name, period)

    # ⑥ K线图
    st.divider()
    plot_candlestick_chart(data)

    # ⑦ MACD
    with st.expander("MACD 指标", expanded=False):
        _render_chart_header("MACD", latest_indicator_values(data, "macd"))
        fig = plot_macd_chart(data)
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    # ⑧ RSI + KDJ 并排
    with st.expander("RSI & KDJ 指标", expanded=False):
        col_rsi, col_kdj = st.columns(2)
        with col_rsi:
            _render_chart_header("RSI", latest_indicator_values(data, "rsi"))
            fig = plot_rsi_chart(data)
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        with col_kdj:
            _render_chart_header("KDJ", latest_indicator_values(data, "kdj"))
            fig = plot_kdj_chart(data)
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    # ⑨ 布林带
    with st.expander("布林带", expanded=False):
        _render_chart_header("BOLL", latest_indicator_values(data, "boll"))
        fig = plot_boll_chart(data)
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    # ⑩ 原始数据
    with st.expander("查看原始数据"):
        st.dataframe(data.tail(20))


def _render_analysis_loading(container, symbol, market, step, percent):
    """渲染分析中的友好占位卡片，避免搜索后页面空白。"""
    market_label = {"CN": "A股", "US": "美股", "HK": "港股"}.get(market, market)
    safe_symbol = html.escape(str(symbol or "--"))
    safe_step = html.escape(str(step or "准备分析"))
    percent = max(0, min(100, int(percent)))
    with container.container():
        st.markdown(
            f"""
            <div class="analysis-loading-card">
              <div class="analysis-loading-header">
                <div>
                  <div class="analysis-loading-kicker">正在分析 · {html.escape(market_label)}</div>
                  <div class="analysis-loading-title">{safe_symbol}</div>
                </div>
                <div class="analysis-loading-percent">{percent}%</div>
              </div>
              <div class="analysis-loading-bar">
                <div style="width:{percent}%"></div>
              </div>
              <div class="analysis-loading-step">{safe_step}</div>
              <div class="analysis-loading-hint">正在并发获取行情、基础资料和扩展信息。慢的时候通常是外部数据源响应较慢，不是页面卡住。</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def analyze_stock_page():
    """个股分析页面"""
    st.markdown('<h1 class="main-header">股票技术分析</h1>', unsafe_allow_html=True)

    if 'analyze_symbol' not in st.session_state:
        st.session_state.analyze_symbol = "000001"
    if 'analyze_symbol_input' not in st.session_state:
        st.session_state.analyze_symbol_input = "000001"
    if 'analyze_market' not in st.session_state:
        st.session_state.analyze_market = "CN"
    if 'analyze_period' not in st.session_state:
        st.session_state.analyze_period = "1y"
    if 'analyze_selected_suggestion' not in st.session_state:
        st.session_state.analyze_selected_suggestion = ""
    if 'quick_stock_query' not in st.session_state:
        st.session_state.quick_stock_query = ""
    pending_quick_match = st.session_state.pop("pending_quick_match", None)
    if pending_quick_match:
        st.session_state.analyze_symbol = pending_quick_match["symbol"]
        st.session_state.analyze_symbol_input = pending_quick_match["symbol"]
        st.session_state.quick_stock_query = ""
        st.session_state.trigger_analysis = True
        st.session_state.quick_match_caption = (
            f"已选择：{pending_quick_match['name']} ({pending_quick_match['symbol']})"
        )

    def on_market_change():
        st.session_state.analyze_market = st.session_state.analyze_market_select

    def on_period_change():
        st.session_state.analyze_period = st.session_state.analyze_period_select

    # ================================================================
    # 搜索区域 — 主搜索框 + 辅助选项
    # ================================================================

    # 第1行：搜索框 | 开始分析（核心操作，视觉焦点）
    # 用 st.form 包住：表单提交时保证所有值批量发送，不依赖输入框的 dirty 标记
    with st.form("search_form"):
        col_input, col_btn = st.columns([5, 1])
        with col_input:
            st.caption("支持输入股票代码或名称，例如：000001、平安银行、贵州茅台、AAPL、00700")
            st.text_input(
                "股票代码或名称",
                placeholder="000001 或 平安银行 · AAPL · 00700",
                key="analyze_symbol_input",
            )
        with col_btn:
            submitted = st.form_submit_button(
                "开始分析", type="primary", use_container_width=True
            )

    if submitted:
        st.session_state.analyze_symbol = st.session_state.analyze_symbol_input
        st.session_state.trigger_analysis = True

    current_header_name = st.session_state.get("analyzed_stock_name")
    current_header_symbol = st.session_state.get("analyze_symbol_input", st.session_state.analyze_symbol)
    if st.session_state.get("analyzed_data") is None:
        target = _resolve_watchlist_target(current_header_symbol, st.session_state.analyze_market)
        if target:
            current_header_symbol, current_header_name = target
    _render_current_stock_header(
        current_header_symbol,
        st.session_state.analyze_market,
        st.session_state.analyze_period,
        current_header_name,
    )

    quick_match_caption = st.session_state.pop("quick_match_caption", None)
    if quick_match_caption:
        st.caption(quick_match_caption)

    st.text_input(
        "快速匹配",
        placeholder="输入股票名称、简称或代码，例如：瑞鹄、茅台、002997",
        key="quick_stock_query",
    )
    quick_query = st.session_state.get("quick_stock_query", "").strip()
    suggestions = suggest_stock_inputs(
        quick_query or st.session_state.get("analyze_symbol_input", ""),
        st.session_state.get("analyze_market", "CN"),
    )
    if quick_query and suggestions:
        st.markdown('<div class="quick-match-row">', unsafe_allow_html=True)
        columns = st.columns(min(4, len(suggestions)))
        for index, item in enumerate(suggestions):
            with columns[index % len(columns)]:
                if st.button(item["label"], key=f"quick_match_{item['symbol']}", use_container_width=True):
                    st.session_state.pending_quick_match = {
                        "symbol": item["symbol"],
                        "name": item["name"],
                    }
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    elif quick_query:
        st.caption("没有找到本地候选；可以直接点「开始分析」，系统会尝试联网解析。")

    # 第2行：市场 | 周期 | 配色 | 自选 | 刷新 — 总宽7份，保留结果加载前的自选入口
    col_mkt, col_period, col_pref, col_watch_quick, col_refresh = st.columns([2, 2, 1, 1, 1])

    with col_mkt:
        market_index = ["CN", "US", "HK"].index(st.session_state.analyze_market)
        market = st.selectbox(
            "市场",
            options=["CN", "US", "HK"],
            index=market_index,
            format_func=lambda x: {"CN": "A股", "US": "美股", "HK": "港股"}[x],
            key="analyze_market_select",
            on_change=on_market_change,
        )

    with col_period:
        period_options = ["1wk", "1mo", "3mo", "6mo", "1y", "2y"]
        period_labels = {
            "1wk": "1周 · 短线异动",
            "1mo": "1个月 · 短线择时",
            "3mo": "3个月 · 波段确认",
            "6mo": "6个月 · 趋势判断",
            "1y": "1年 · 长线布局",
            "2y": "2年 · 历史锚点",
        }
        period_index = period_options.index(st.session_state.analyze_period)
        period = st.selectbox(
            "周期",
            options=period_options,
            index=period_index,
            format_func=lambda x: period_labels[x],
            key="analyze_period_select",
            on_change=on_period_change,
        )

    with col_pref:
        if "color_scheme" not in st.session_state:
            st.session_state.color_scheme = DEFAULT_COLOR_SCHEME.get(
                st.session_state.analyze_market, "red_up"
            )

        def on_color_scheme_change():
            st.session_state.color_scheme = st.session_state.color_scheme_select

        scheme_options = list(COLOR_SCHEMES.keys())
        scheme_labels = {k: v["label"] for k, v in COLOR_SCHEMES.items()}
        scheme_index = scheme_options.index(st.session_state.color_scheme)
        st.selectbox(
            "配色",
            options=scheme_options,
            index=scheme_index,
            format_func=lambda x: scheme_labels[x],
            key="color_scheme_select",
            on_change=on_color_scheme_change,
        )

    with col_watch_quick:
        st.markdown('<div class="select-row-button-spacer"></div>', unsafe_allow_html=True)
        _render_watchlist_quick_action(
            st.session_state.get("analyze_symbol_input", st.session_state.analyze_symbol),
            st.session_state.analyze_market,
        )

    with col_refresh:
        # 占位高度 = selectbox 标签高度，让按钮与下拉框对齐
        st.markdown('<div class="select-row-button-spacer"></div>', unsafe_allow_html=True)
        if st.button("刷新缓存", type="secondary", use_container_width=True):
            get_cached_stock_data.clear()
            get_cached_realtime_quote.clear()
            get_cached_stock_info.clear()
            get_cached_intraday_data.clear()
            resolve_cached_stock_input.clear()
            st.success("已清除缓存，请重新分析")

    symbol = st.session_state.analyze_symbol
    market = st.session_state.analyze_market
    period = st.session_state.analyze_period

    analyze_clicked = st.session_state.pop('trigger_analysis', False)

    if analyze_clicked:
        loading_panel = st.empty()
        _render_analysis_loading(loading_panel, symbol, market, "正在识别输入并准备分析...", 2)

        # 名称→代码解析（A股支持输入中文名称）
        resolved_name = None
        has_chinese = any('一' <= c <= '鿿' for c in symbol)
        if market == "CN" and not (symbol.isdigit() and len(symbol) == 6):
            if has_chinese:
                _render_analysis_loading(loading_panel, symbol, market, "正在按股票名称匹配代码...", 8)
                result = resolve_cached_stock_input(symbol, market)
                if result:
                    resolved_name = result[1]
                    symbol = result[0]
                    st.session_state.analyze_symbol = symbol
                    st.caption(f"已识别: {resolved_name} ({symbol})")
                else:
                    st.error(f"未找到匹配「{symbol}」的股票，请使用6位代码搜索或检查名称是否正确")
                    loading_panel.empty()
                    st.stop()
            else:
                _render_analysis_loading(loading_panel, symbol, market, "正在解析股票代码...", 8)
                result = resolve_cached_stock_input(symbol, market)
                if result:
                    resolved_name = result[1]
                    symbol = result[0]
                    st.session_state.analyze_symbol = symbol
                    st.caption(f"已识别: {resolved_name} ({symbol})")

        is_valid, err_msg = _validate_symbol(symbol, market)
        if not is_valid:
            st.error(f"输入的股票代码格式有误，{err_msg}")
            loading_panel.empty()
            st.stop()

        _render_analysis_loading(loading_panel, symbol, market, "正在并发获取股票数据...", 12)

        info = {'shortName': symbol, 'symbol': symbol}
        data = None
        quote = None
        intraday_data = None
        profile = None
        extended_info = None

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=6)
        futures = {}
        try:
            futures = {
                'info': executor.submit(get_cached_stock_info, symbol, market),
                'data': executor.submit(get_cached_stock_data, symbol, '1y', market),
                'quote': executor.submit(get_cached_realtime_quote, symbol, market),
            }
            if market == "CN":
                futures['intraday'] = executor.submit(get_cached_intraday_data, symbol, market)
                futures['profile'] = executor.submit(get_cached_stock_profile, symbol, market)
                futures['extended_info'] = executor.submit(get_cached_stock_extended_info, symbol, market)

            try:
                data = futures['data'].result(timeout=20)
            except Exception:
                data = None
            _render_analysis_loading(loading_panel, symbol, market, "历史行情已返回，正在读取股票资料...", 45)

            try:
                info_result = futures['info'].result(timeout=0.2)
                if info_result:
                    info = info_result
            except Exception:
                info = {'shortName': symbol, 'symbol': symbol}
            _render_analysis_loading(loading_panel, symbol, market, "正在获取实时行情...", 50)

            try:
                quote = futures['quote'].result(timeout=0.2)
            except Exception:
                quote = None
            _render_analysis_loading(loading_panel, symbol, market, "正在补充基础资料、分时和扩展信息...", 55)

            try:
                if 'intraday' in futures:
                    intraday_data = futures['intraday'].result(timeout=0.2)
            except Exception:
                intraday_data = None

            try:
                if 'profile' in futures:
                    profile = futures['profile'].result(timeout=2.5)
            except Exception:
                profile = {"loading": True, "source": "基础资料服务"}

            try:
                if 'extended_info' in futures:
                    extended_info = futures['extended_info'].result(timeout=2.5)
            except Exception:
                extended_info = {"loading": True, "source": "AKShare"}
        finally:
            for future in futures.values():
                if not future.done():
                    future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
        if data is None or data.empty:
            st.error(f"未能获取到 {symbol} 的数据，请检查：\n1. 股票代码是否正确\n2. 市场选择是否正确\n3. 网络连接是否正常")
            loading_panel.empty()
            return

        data_source = data.attrs.get('data_source', '未知')
        offline_mode = data.attrs.get('offline_mode', False)
        is_fallback = "AKShare" not in data_source and not offline_mode

        if offline_mode:
            st.caption(f"🔴 离线缓存 · {data_source}")
        elif is_fallback:
            st.caption(f"🟡 备选数据源 · {data_source}")
        else:
            st.caption(f"数据源 · {data_source}")

        _render_analysis_loading(loading_panel, symbol, market, "正在合并实时行情...", 65)
        if quote and data is not None and not data.empty:
            today = pd.Timestamp.now().normalize()
            if data.index[-1].normalize() == today:
                idx = data.index[-1]
                data.loc[idx, 'close'] = quote['price']
                data.loc[idx, 'high'] = max(data.loc[idx, 'high'], quote['high'])
                data.loc[idx, 'low'] = min(data.loc[idx, 'low'], quote['low'])
                data.loc[idx, 'volume'] = quote.get('volume', data.loc[idx, 'volume'])
            else:
                realtime_row = pd.DataFrame({
                    'open': [quote['open']],
                    'high': [quote['high']],
                    'low': [quote['low']],
                    'close': [quote['price']],
                    'volume': [quote['volume']]
                }, index=[pd.Timestamp.now()])
                data = pd.concat([data, realtime_row])
        _render_analysis_loading(loading_panel, symbol, market, "正在识别股票名称和检查数据完整性...", 75)
        stock_name = resolved_name or symbol
        if isinstance(info, dict):
            stock_name = info.get('shortName') or info.get('longName') or stock_name
        if stock_name == symbol and market == "CN":
            name_result = resolve_cached_stock_input(symbol, market)
            if name_result:
                stock_name = name_result[1]
        elif stock_name == symbol:
            stock_name = symbol

        short_history_notice = _build_short_history_notice(symbol, stock_name, len(data), period)
        if short_history_notice:
            st.info(short_history_notice)

        _render_analysis_loading(loading_panel, symbol, market, "正在计算技术指标（MACD/RSI/KDJ/BOLL/MA）...", 82)
        data = TechnicalIndicators.calculate_all(data)

        _render_analysis_loading(loading_panel, symbol, market, "正在生成交易信号和决策仪表盘...", 92)
        signals = TechnicalIndicators.get_signals(data)

        if 'error' in signals:
            st.warning(f"指标计算问题：{signals['error']}")

        _render_analysis_loading(loading_panel, symbol, market, "正在渲染图表...", 99)

        st.session_state.analyzed_data = data
        st.session_state.analyzed_signals = signals
        st.session_state.analyzed_quote = quote
        st.session_state.analyzed_stock_name = stock_name
        st.session_state.analyzed_profile = profile
        st.session_state.analyzed_extended_info = extended_info

        period_days = {'1wk': 7, '1mo': 30, '3mo': 90, '6mo': 180, '1y': 365, '2y': 730}
        cutoff = data.index[-1] - pd.Timedelta(days=period_days.get(period, 365))
        display_data = data[data.index >= cutoff] if len(data[data.index >= cutoff]) >= 10 else data

        _render_analysis_results(display_data, signals, quote, symbol, stock_name, market, period, intraday_data=intraday_data, profile=profile, extended_info=extended_info)

        loading_panel.empty()

    # rerun 恢复
    if not analyze_clicked:
        cached_data = st.session_state.get("analyzed_data")
        if cached_data is not None:
            period_days = {'1wk': 7, '1mo': 30, '3mo': 90, '6mo': 180, '1y': 365, '2y': 730}
            cutoff = cached_data.index[-1] - pd.Timedelta(days=period_days.get(period, 365))
            display_data = cached_data[cached_data.index >= cutoff] if len(cached_data[cached_data.index >= cutoff]) >= 10 else cached_data
            _render_analysis_results(
                display_data,
                st.session_state.get("analyzed_signals", {}),
                st.session_state.get("analyzed_quote"),
                symbol,
                st.session_state.get("analyzed_stock_name", ""),
                market,
                period,
                profile=st.session_state.get("analyzed_profile"),
                extended_info=st.session_state.get("analyzed_extended_info"),
            )

    # 锚点滚动
    if st.session_state.pop('scroll_to_results', False):
        st.components.v1.html("""
        <script>
            var el = parent.document.getElementById('analysis-results');
            if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
        </script>
        """, height=0)
