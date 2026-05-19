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
from ui.loading import make_progress_reporter
from ui.stock_search import suggest_stock_inputs
from quality_monitor import build_stock_data_quality_summary


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


def _safe_number(value):
    try:
        if value is None:
            return None
        number = float(value)
        if np.isnan(number) or np.isinf(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def _is_valid_quote(quote):
    """过滤实时行情接口返回的 0 价/空价，避免覆盖真实 K 线收盘价。"""
    if not isinstance(quote, dict):
        return False
    price = _safe_number(quote.get("price"))
    if price is None or price <= 0:
        return False
    high = _safe_number(quote.get("high"))
    low = _safe_number(quote.get("low"))
    open_price = _safe_number(quote.get("open"))
    if high is not None and high <= 0:
        return False
    if low is not None and low <= 0:
        return False
    if open_price is not None and open_price <= 0:
        return False
    return True


def _quote_from_last_row(data):
    """实时行情不可用时，用历史 K 线最后一根生成真实兜底 quote。"""
    if data is None or data.empty:
        return None
    last_row = data.iloc[-1]
    price = _safe_number(last_row.get("close"))
    if price is None or price <= 0:
        return None
    prev_row = data.iloc[-2] if len(data) > 1 else last_row
    prev_close = _safe_number(prev_row.get("close"))
    change = (price - prev_close) / prev_close * 100 if prev_close and prev_close > 0 else 0
    return {
        "price": price,
        "high": _safe_number(last_row.get("high")) or price,
        "low": _safe_number(last_row.get("low")) or price,
        "open": _safe_number(last_row.get("open")) or price,
        "volume": int(_safe_number(last_row.get("volume")) or 0),
        "change": change,
        "source": "历史K线兜底",
    }


def _normalize_target_symbol(symbol, market):
    text = str(symbol or "").strip()
    if market == "CN" and text.isdigit():
        return text.zfill(6)
    if market == "HK" and text.isdigit():
        return text.zfill(5)
    return text.upper() if text.isascii() else text


def _analysis_target_key(symbol, market, period):
    return (
        _normalize_target_symbol(symbol, market),
        str(market or ""),
        str(period or ""),
    )


def _quote_matches_target(quote, symbol, market):
    if not isinstance(quote, dict):
        return False
    quote_symbol = quote.get("symbol") or quote.get("code")
    if not quote_symbol:
        return False
    expected = _normalize_target_symbol(symbol, market)
    raw_actual = str(quote_symbol).strip()
    actual_parts = [
        raw_actual,
        raw_actual.split(".", 1)[0],
        raw_actual.split("_", 1)[0],
    ]
    actual_values = [_normalize_target_symbol(part, market) for part in actual_parts if part]
    if market in ("CN", "HK"):
        return any(actual.endswith(expected) for actual in actual_values)
    return any(actual == expected for actual in actual_values)


def _quote_for_target(quote, symbol, market, data):
    if _is_valid_quote(quote) and _quote_matches_target(quote, symbol, market):
        return quote
    return _quote_from_last_row(data)


def _tag_analysis_data(data, symbol, market, period):
    if data is not None and hasattr(data, "attrs"):
        data.attrs["analysis_target_key"] = _analysis_target_key(symbol, market, period)
    return data


def _data_matches_target(data, symbol, market, period):
    if data is None or not hasattr(data, "attrs"):
        return False
    return data.attrs.get("analysis_target_key") == _analysis_target_key(symbol, market, period)


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
            "可能是新股/次新股或数据源只返回上市后行情。长周期指标（如 MA20/MA30、RSI24、BOLL）"
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


def _render_data_quality_summary(data, quote, profile, extended_info):
    summary = build_stock_data_quality_summary(data, quote, profile, extended_info)
    issues = summary.get("issues") or []
    warnings = summary.get("warnings") or []
    if not issues and not warnings:
        st.caption(f"数据完整性：主要行情、指标和扩展信息已就绪（K线 {summary.get('data_rows', 0)} 条）。")
        return
    with st.expander("数据质量 / 风险提示", expanded=bool(issues)):
        col_rows, col_status = st.columns(2)
        col_rows.metric("K线数量", summary.get("data_rows", 0))
        col_status.metric("状态", {"risk": "需关注", "partial": "部分缺失", "ok": "完整"}.get(summary.get("status"), "--"))
        if issues:
            st.markdown("**风险提示**")
            st.markdown("\n".join(f"- {html.escape(str(item))}" for item in issues))
        if warnings:
            st.markdown("**数据缺口**")
            st.markdown("\n".join(f"- {html.escape(str(item))}" for item in warnings[:8]))


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
    ma30 = _format_val(latest, 'ma30', 2)
    if ma5 != '--':
        st.markdown(
            f'<div style="{card}border-left:3px solid #8e8e93;">'
            f'<span><b style="margin-right:10px;">均线</b>'
            f'<span>MA5 {ma5}</span>  '
            f'<span>MA10 {ma10}</span>  '
            f'<span>MA20 {ma20}</span>  '
            f'<span>MA30 {ma30}</span></span>'
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


def _get_analyzed_target():
    """返回已完成分析对应的代码、名称、市场和周期。"""
    if not _has_valid_analyzed_result():
        return None
    symbol = st.session_state.get("analyzed_symbol") or st.session_state.get("analyze_symbol")
    market = st.session_state.get("analyzed_market") or st.session_state.get("analyze_market", "CN")
    period = st.session_state.get("analyzed_period") or st.session_state.get("analyze_period", "1y")
    stock_name = st.session_state.get("analyzed_stock_name") or symbol
    return symbol, stock_name, market, period


def _clear_analyzed_result():
    """清除已完成分析缓存，避免新输入时旧结果串台。"""
    for key in [
        "analyzed_symbol",
        "analyzed_market",
        "analyzed_period",
        "analyzed_target_key",
        "analyzed_data",
        "analyzed_signals",
        "analyzed_quote",
        "analyzed_stock_name",
        "analyzed_profile",
        "analyzed_extended_info",
        "analyzed_intraday_data",
        "pending_analyze_input_sync",
    ]:
        st.session_state.pop(key, None)


def _is_current_input_analyzed():
    """判断当前输入框/市场/周期是否仍对应已完成分析结果。"""
    if not _has_valid_analyzed_result():
        return False
    target = _resolve_watchlist_target(
        st.session_state.get("analyze_symbol_input", st.session_state.get("analyze_symbol", "")),
        st.session_state.get("analyze_market", "CN"),
    )
    input_symbol = target[0] if target else str(st.session_state.get("analyze_symbol_input", "")).strip()
    return _analysis_target_key(
        input_symbol,
        st.session_state.get("analyze_market"),
        st.session_state.get("analyze_period"),
    ) == st.session_state.get("analyzed_target_key")


def _has_valid_analyzed_result():
    """确保已分析缓存自身的 symbol/market/period 归属完整，避免切页回来串台。"""
    if st.session_state.get("analyzed_data") is None:
        return False
    symbol = st.session_state.get("analyzed_symbol")
    market = st.session_state.get("analyzed_market")
    period = st.session_state.get("analyzed_period")
    if not symbol or not market or not period:
        return False
    expected = _analysis_target_key(symbol, market, period)
    if not _data_matches_target(st.session_state.get("analyzed_data"), symbol, market, period):
        return False
    stored = st.session_state.get("analyzed_target_key")
    if stored is None:
        st.session_state.analyzed_target_key = expected
        return True
    return stored == expected


def _sync_analyze_input_to_cached_result():
    """页面切回个股分析时，确保顶部输入/当前标的与已分析结果一致。"""
    if not _has_valid_analyzed_result():
        return
    analyzed_symbol = st.session_state.get("analyzed_symbol")
    analyzed_market = st.session_state.get("analyzed_market")
    analyzed_period = st.session_state.get("analyzed_period")
    if not analyzed_symbol:
        return
    st.session_state.analyze_symbol = analyzed_symbol
    st.session_state.analyze_symbol_input = analyzed_symbol
    if analyzed_market:
        st.session_state.analyze_market = analyzed_market
        st.session_state.analyze_market_select = analyzed_market
    if analyzed_period:
        st.session_state.analyze_period = analyzed_period
        st.session_state.analyze_period_select = analyzed_period


def _render_analysis_target_header(symbol, stock_name, market, period, *, show_watchlist=True):
    """统一展示股票代码和股票名称，避免页面出现两个标的栏。"""
    display_name = stock_name if stock_name and stock_name != symbol else ""
    market_label = {"CN": "A股", "US": "美股", "HK": "港股"}.get(market, market)
    col_title, col_watchlist = st.columns([3, 1]) if show_watchlist else (st.container(), None)
    with col_title:
        st.markdown(
            f"""
            <div style="margin:0 0 12px;padding:14px 16px;border-radius:14px;
                        border:1px solid rgba(85,199,255,0.18);
                        background:linear-gradient(135deg,rgba(85,199,255,0.13),rgba(5,13,24,0.78));
                        box-shadow:0 12px 30px rgba(0,0,0,0.20);">
              <div style="font-size:0.82rem;opacity:0.65;margin-bottom:4px;">当前分析标的</div>
              <div style="font-size:1.32rem;font-weight:700;line-height:1.3;">
                {html.escape(str(symbol or "--"))}{f" · {html.escape(str(display_name))}" if display_name else ""}
              </div>
              <div style="font-size:0.85rem;opacity:0.65;margin-top:4px;">{html.escape(market_label)} · {html.escape(str(period))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    if show_watchlist and col_watchlist is not None:
        with col_watchlist:
            if is_in_watchlist(symbol, market):
                if st.button("移除自选", key=f"remove_watchlist_{market}_{symbol}"):
                    success, msg = remove_from_watchlist(symbol, market)
                    if success:
                        st.success(msg)
                        st.rerun()
            else:
                if st.button("加入自选", key=f"add_watchlist_{market}_{symbol}"):
                    success, msg = add_to_watchlist(symbol, stock_name, market)
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.warning(msg)


def _render_analysis_results(data, signals, quote, symbol, stock_name, market, period, intraday_data=None, profile=None, extended_info=None):
    """渲染个股分析结果 — Apple×Tesla 分层布局"""
    st.markdown('<div id="analysis-results"></div>', unsafe_allow_html=True)
    st.divider()


    # ② 核心指标 — 最新价
    if not _is_valid_quote(quote):
        quote = _quote_from_last_row(data)

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
    _render_data_quality_summary(data, quote, profile, extended_info)

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


def _emit_progress(progress_callback, stage, percent, **metrics):
    if not callable(progress_callback):
        return
    try:
        progress_callback(stage, percent, metrics)
    except Exception:
        pass


def _run_stock_analysis_task(symbol, market, period, progress_callback=None):
    """后台执行个股分析，避免切页中断并确保代码/名称成对写回。"""
    original_query = str(symbol or "").strip()
    symbol = original_query
    resolved_name = None
    _emit_progress(progress_callback, "解析输入", 5, query=original_query, market=market)

    has_chinese = any('一' <= c <= '鿿' for c in symbol)
    if market == "CN" and not (symbol.isdigit() and len(symbol) == 6):
        _emit_progress(progress_callback, "解析股票名称", 10, query=original_query)
        result = resolve_cached_stock_input(symbol, market)
        if result:
            resolved_name = result[1]
            symbol = result[0]
        elif has_chinese:
            return {
                "error": f"未找到匹配「{symbol}」的股票，请使用6位代码搜索或检查名称是否正确",
                "query": original_query,
                "market": market,
                "period": period,
            }

    is_valid, err_msg = _validate_symbol(symbol, market)
    _emit_progress(progress_callback, "校验代码", 15, symbol=symbol)
    if not is_valid:
        return {
            "error": f"输入的股票代码格式有误，{err_msg}",
            "query": original_query,
            "symbol": symbol,
            "market": market,
            "period": period,
        }

    info = {'shortName': symbol, 'symbol': symbol}
    data = None
    quote = None
    intraday_data = None
    profile = None
    extended_info = None

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=6)
    futures = {}
    try:
        _emit_progress(progress_callback, "提交行情任务", 22, symbol=symbol)
        futures = {
            'info': executor.submit(get_cached_stock_info, symbol, market),
            'data': executor.submit(get_cached_stock_data, symbol, '1y', market, 'qfq' if market == "CN" else ""),
            'quote': executor.submit(get_cached_realtime_quote, symbol, market),
        }
        if market == "CN":
            futures['intraday'] = executor.submit(get_cached_intraday_data, symbol, market)
            futures['profile'] = executor.submit(get_cached_stock_profile, symbol, market)
            futures['extended_info'] = executor.submit(get_cached_stock_extended_info, symbol, market)

        completed = 0
        total = len(futures)

        try:
            data = futures['data'].result(timeout=20)
        except Exception:
            data = None
        completed += 1
        _emit_progress(progress_callback, "历史K线完成", 45, done=completed, total=total)

        try:
            info_result = futures['info'].result(timeout=0.2)
            if info_result:
                info = info_result
        except Exception:
            info = {'shortName': symbol, 'symbol': symbol}
        completed += 1
        _emit_progress(progress_callback, "基础信息完成", 52, done=completed, total=total)

        try:
            quote = futures['quote'].result(timeout=0.2)
        except Exception:
            quote = None
        completed += 1
        _emit_progress(progress_callback, "实时行情完成", 60, done=completed, total=total)

        try:
            if 'intraday' in futures:
                intraday_data = futures['intraday'].result(timeout=0.2)
        except Exception:
            intraday_data = None
        if 'intraday' in futures:
            completed += 1
            _emit_progress(progress_callback, "分时数据完成", 68, done=completed, total=total)

        try:
            if 'profile' in futures:
                profile = futures['profile'].result(timeout=2.5)
        except Exception:
            profile = {"loading": True, "source": "基础资料服务"}
        if 'profile' in futures:
            completed += 1
            _emit_progress(progress_callback, "基础资料完成", 76, done=completed, total=total)

        try:
            if 'extended_info' in futures:
                extended_info = futures['extended_info'].result(timeout=2.5)
        except Exception:
            extended_info = {"loading": True, "source": "AKShare"}
        if 'extended_info' in futures:
            completed += 1
            _emit_progress(progress_callback, "扩展资料完成", 82, done=completed, total=total)
    finally:
        for future in futures.values():
            if not future.done():
                future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)

    if data is None or data.empty:
        return {
            "error": f"未能获取到 {symbol} 的数据，请检查股票代码、市场选择或网络连接",
            "query": original_query,
            "symbol": symbol,
            "market": market,
            "period": period,
        }

    quote_is_realtime = _is_valid_quote(quote) and _quote_matches_target(quote, symbol, market)
    if not quote_is_realtime:
        _emit_progress(progress_callback, "实时行情兜底", 84, source="历史K线")
        quote = _quote_from_last_row(data)

    if quote_is_realtime:
        _emit_progress(progress_callback, "实时行情完成", 88)

    stock_name = resolved_name or symbol
    if isinstance(info, dict):
        stock_name = info.get('shortName') or info.get('longName') or stock_name
    if stock_name == symbol and market == "CN":
        name_result = resolve_cached_stock_input(symbol, market)
        if name_result:
            stock_name = name_result[1]
    elif stock_name == symbol:
        stock_name = symbol

    _emit_progress(progress_callback, "计算技术指标", 94)
    data = TechnicalIndicators.calculate_all(data)
    data = _tag_analysis_data(data, symbol, market, period)
    _emit_progress(progress_callback, "生成交易信号", 98)
    signals = TechnicalIndicators.get_signals(data)

    _emit_progress(progress_callback, "完成", 100, symbol=symbol)
    return {
        "query": original_query,
        "symbol": symbol,
        "market": market,
        "period": period,
        "stock_name": stock_name,
        "data": data,
        "signals": signals,
        "quote": quote,
        "intraday_data": intraday_data,
        "profile": profile,
        "extended_info": extended_info,
    }


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
    pending_analyze_input_sync = st.session_state.pop("pending_analyze_input_sync", None)
    if pending_analyze_input_sync:
        st.session_state.analyze_symbol = pending_analyze_input_sync["symbol"]
        st.session_state.analyze_symbol_input = pending_analyze_input_sync["symbol"]
        st.session_state.analyze_market = pending_analyze_input_sync.get("market", st.session_state.analyze_market)
        st.session_state.analyze_market_select = st.session_state.analyze_market
        st.session_state.analyze_period = pending_analyze_input_sync.get("period", st.session_state.analyze_period)
        st.session_state.analyze_period_select = st.session_state.analyze_period
    pending_watchlist_analysis = st.session_state.pop("pending_watchlist_analysis", None)
    if pending_watchlist_analysis:
        st.session_state.analyze_symbol = pending_watchlist_analysis["symbol"]
        st.session_state.analyze_symbol_input = pending_watchlist_analysis["symbol"]
        st.session_state.analyze_market = pending_watchlist_analysis.get("market", "CN")
        st.session_state.analyze_market_select = st.session_state.analyze_market
        st.session_state.quick_stock_query = ""
        st.session_state.trigger_analysis = True
        st.session_state.scroll_to_results = True
        st.session_state.quick_match_caption = (
            f"已从自选股打开：{pending_watchlist_analysis.get('name') or pending_watchlist_analysis['symbol']} "
            f"({pending_watchlist_analysis['symbol']})"
        )
        _clear_analyzed_result()
    pending_quick_match = st.session_state.pop("pending_quick_match", None)
    if pending_quick_match:
        st.session_state.analyze_symbol = pending_quick_match["symbol"]
        st.session_state.analyze_symbol_input = pending_quick_match["symbol"]
        st.session_state.quick_stock_query = ""
        st.session_state.trigger_analysis = True
        st.session_state.quick_match_caption = (
            f"已选择：{pending_quick_match['name']} ({pending_quick_match['symbol']})"
        )
    if not pending_watchlist_analysis and not pending_quick_match:
        _sync_analyze_input_to_cached_result()

    def on_market_change():
        st.session_state.analyze_market = st.session_state.analyze_market_select
        _clear_analyzed_result()

    def on_period_change():
        st.session_state.analyze_period = st.session_state.analyze_period_select
        _clear_analyzed_result()

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
        _clear_analyzed_result()

    analyzed_target = _get_analyzed_target() if _is_current_input_analyzed() else None
    if analyzed_target:
        _render_analysis_target_header(*analyzed_target)
    else:
        current_header_name = None
        current_header_symbol = st.session_state.get("analyze_symbol_input", st.session_state.analyze_symbol)
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
        _clear_analyzed_result()
        loading_panel = st.empty()
        market_label = {"CN": "A股", "US": "美股", "HK": "港股"}.get(market, market)
        progress = make_progress_reporter(
            loading_panel,
            "正在分析个股",
            context=f"{symbol} · {market_label}",
        )
        progress.update("启动", 3)
        task_result = _run_stock_analysis_task(
            symbol,
            market,
            period,
            progress_callback=lambda stage, percent, metrics=None: progress.update(stage, percent, metrics),
        )
        loading_panel.empty()
        if task_result.get("error"):
            st.error(task_result["error"])
        else:
            symbol = task_result["symbol"]
            market = task_result["market"]
            period = task_result["period"]
            data = _tag_analysis_data(task_result["data"], symbol, market, period)
            st.session_state.analyze_symbol = symbol
            st.session_state.analyzed_symbol = symbol
            st.session_state.analyzed_market = market
            st.session_state.analyzed_period = period
            st.session_state.analyzed_target_key = _analysis_target_key(symbol, market, period)
            st.session_state.analyzed_data = data
            st.session_state.analyzed_signals = task_result["signals"]
            st.session_state.analyzed_quote = task_result["quote"]
            st.session_state.analyzed_stock_name = task_result["stock_name"]
            st.session_state.analyzed_profile = task_result["profile"]
            st.session_state.analyzed_extended_info = task_result["extended_info"]
            st.session_state.analyzed_intraday_data = task_result["intraday_data"]
            st.session_state.pending_analyze_input_sync = {
                "symbol": symbol,
                "market": market,
                "period": period,
            }
            st.rerun()

    # rerun 恢复
    has_fresh_task_result = (
        _has_valid_analyzed_result()
        and _analysis_target_key(
            st.session_state.get("analyze_symbol"),
            st.session_state.get("analyze_market"),
            st.session_state.get("analyze_period"),
        ) == st.session_state.get("analyzed_target_key")
    )
    if _is_current_input_analyzed() or has_fresh_task_result:
        cached_data = st.session_state.get("analyzed_data")
        if cached_data is not None:
            cached_symbol = st.session_state.get("analyzed_symbol", st.session_state.analyze_symbol)
            cached_market = st.session_state.get("analyzed_market", market)
            cached_period = st.session_state.get("analyzed_period", period)
            period_days = {'1wk': 7, '1mo': 30, '3mo': 90, '6mo': 180, '1y': 365, '2y': 730}
            cutoff = cached_data.index[-1] - pd.Timedelta(days=period_days.get(cached_period, 365))
            display_data = cached_data[cached_data.index >= cutoff] if len(cached_data[cached_data.index >= cutoff]) >= 10 else cached_data
            _render_analysis_results(
                display_data,
                st.session_state.get("analyzed_signals", {}),
                _quote_for_target(st.session_state.get("analyzed_quote"), cached_symbol, cached_market, display_data),
                cached_symbol,
                st.session_state.get("analyzed_stock_name", ""),
                cached_market,
                cached_period,
                intraday_data=st.session_state.get("analyzed_intraday_data"),
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
