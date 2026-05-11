"""个股分析页面 — 输入表单 + 数据获取 + 结果渲染"""
import html
import concurrent.futures
import streamlit as st
import pandas as pd
import numpy as np
from config import (
    RSI_OVERBOUGHT, RSI_OVERSOLD, KDJ_OVERBOUGHT, KDJ_OVERSOLD,
    DEFAULT_COLOR_SCHEME, COLOR_SCHEMES, AI_ENABLED,
)
from technical_indicators import TechnicalIndicators
from watchlist import add_to_watchlist, remove_from_watchlist, is_in_watchlist
from ui.cached_data import (
    fetcher,
    get_cached_stock_data, get_cached_stock_info,
    get_cached_realtime_quote, get_cached_intraday_data,
)
from ui.charts import (
    plot_candlestick_chart, plot_rsi_chart, plot_kdj_chart,
    plot_boll_chart, plot_intraday_chart,
)
from ui.ai_analysis_ui import display_ai_analysis_card


def _classify_signal(text):
    """信号分类：返回 'buy' / 'sell' / 'neutral'"""
    s = str(text)
    if "金叉" in s or "超卖" in s or "反弹" in s or "偏多" in s:
        return "buy"
    if "死叉" in s or "超买" in s or "回调" in s or "偏空" in s:
        return "sell"
    return "neutral"


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


def display_signals(signals):
    """显示交易信号 — 4个徽章横排 + 综合建议"""
    if 'error' in signals:
        st.warning(f"{signals['error']}")
        return

    badges_html = ""
    for key, label in [("MACD", "macd"), ("RSI", "rsi"), ("KDJ", "kdj"), ("布林带", "boll")]:
        text = signals.get(label, '--')
        cls = _classify_signal(text)
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
        "background:rgba(128,128,128,0.04);border-radius:8px;"
        "padding:8px 14px;margin-bottom:6px;"
        "border:1px solid rgba(128,128,128,0.1);"
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
        f'<span style="font-size:0.75rem;color:gray;white-space:nowrap;">超买&gt;{rsi_ob} 超卖&lt;{rsi_os}</span>'
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
        f'<span style="font-size:0.75rem;color:gray;white-space:nowrap;">超买&gt;{kdj_ob} 超卖&lt;{kdj_os}</span>'
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
        f'<span style="font-size:0.75rem;color:gray;white-space:nowrap;">{pct_str}</span>'
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


def _render_analysis_results(data, signals, quote, symbol, stock_name, market, period, intraday_data=None):
    """渲染个股分析结果 — Apple×Tesla 分层布局"""
    st.markdown('<div id="analysis-results"></div>', unsafe_allow_html=True)
    st.divider()

    # ① 标题行
    col_title, col_watchlist = st.columns([3, 1])
    with col_title:
        st.markdown(f'<div style="font-size:1.25rem;font-weight:600;margin-bottom:8px;">{html.escape(symbol)} {html.escape(stock_name)}</div>', unsafe_allow_html=True)
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
                st.info("📌 今日非交易日，暂无分时数据")
            else:
                st.info("📌 分时数据暂不可用，请稍后刷新")

    # ③ 技术指标实时数值卡片
    _display_indicator_values(data)

    st.divider()

    # ④ 交易信号
    display_signals(signals)

    # ⑤ AI 智能解读
    if AI_ENABLED:
        display_ai_analysis_card(data, signals, symbol, stock_name, period)

    # ⑥ K线图
    st.divider()
    plot_candlestick_chart(data)

    # ⑦ RSI + KDJ 并排
    with st.expander("RSI & KDJ 指标", expanded=False):
        col_rsi, col_kdj = st.columns(2)
        with col_rsi:
            st.markdown('<p class="chart-section-title">RSI</p>', unsafe_allow_html=True)
            fig = plot_rsi_chart(data)
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        with col_kdj:
            st.markdown('<p class="chart-section-title">KDJ</p>', unsafe_allow_html=True)
            fig = plot_kdj_chart(data)
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    # ⑧ 布林带
    with st.expander("布林带", expanded=False):
        fig = plot_boll_chart(data)
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    # ⑨ 原始数据
    with st.expander("查看原始数据"):
        st.dataframe(data.tail(20))


def analyze_stock_page():
    """个股分析页面"""
    st.markdown('<h1 class="main-header">股票技术分析</h1>', unsafe_allow_html=True)

    if 'analyze_symbol' not in st.session_state:
        st.session_state.analyze_symbol = "000001"
    if 'analyze_market' not in st.session_state:
        st.session_state.analyze_market = "CN"
    if 'analyze_period' not in st.session_state:
        st.session_state.analyze_period = "1y"

    def on_symbol_change():
        st.session_state.analyze_symbol = st.session_state.analyze_symbol_input

    def on_market_change():
        st.session_state.analyze_market = st.session_state.analyze_market_select

    def on_period_change():
        st.session_state.analyze_period = st.session_state.analyze_period_select

    col1, col2, col3 = st.columns(3)

    with col1:
        symbol = st.text_input("股票代码",
                               value=st.session_state.analyze_symbol,
                               help="A股如: 000001, 600519 | 美股如: AAPL, TSLA",
                               key="analyze_symbol_input",
                               on_change=on_symbol_change)

    with col2:
        market_index = ["CN", "US", "HK"].index(st.session_state.analyze_market)
        market = st.selectbox("市场", options=["CN", "US", "HK"],
                             index=market_index,
                             format_func=lambda x: {"CN": "A股", "US": "美股", "HK": "港股"}[x],
                             key="analyze_market_select",
                             on_change=on_market_change)

    with col3:
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
        period = st.selectbox("时间周期", options=period_options,
                             index=period_index,
                             format_func=lambda x: period_labels[x],
                             key="analyze_period_select",
                             on_change=on_period_change)

    symbol = st.session_state.analyze_symbol
    market = st.session_state.analyze_market
    period = st.session_state.analyze_period

    if 'color_scheme' not in st.session_state:
        st.session_state.color_scheme = DEFAULT_COLOR_SCHEME.get(market, 'red_up')

    def on_color_scheme_change():
        st.session_state.color_scheme = st.session_state.color_scheme_select

    scheme_options = list(COLOR_SCHEMES.keys())
    scheme_labels = {k: v['label'] for k, v in COLOR_SCHEMES.items()}
    scheme_index = scheme_options.index(st.session_state.color_scheme)
    st.selectbox("配色方案", options=scheme_options,
                 index=scheme_index, format_func=lambda x: scheme_labels[x],
                 key="color_scheme_select", on_change=on_color_scheme_change,
                 help="红涨绿跌(A股传统) | 绿涨红跌(国际惯例) | 蓝涨橙跌(色盲友好)")

    col_analyze, col_clear = st.columns([4, 1])
    with col_clear:
        if st.button("刷新数据", type="secondary"):
            get_cached_stock_data.clear()
            get_cached_realtime_quote.clear()
            get_cached_stock_info.clear()
            st.success("已清除缓存，请重新分析")
    with col_analyze:
        analyze_clicked = st.button("开始分析", type="primary", use_container_width=True) or st.session_state.pop('trigger_analysis', False)

    if analyze_clicked:
        is_valid, err_msg = _validate_symbol(symbol, market)
        if not is_valid:
            st.error(f"输入的股票代码格式有误，{err_msg}")
            st.stop()

        progress_bar = st.progress(0)
        status_text = st.empty()

        status_text.text("正在获取股票信息...")
        progress_bar.progress(5)
        info = None
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(get_cached_stock_info, symbol, market)
                info = future.result(timeout=5)
        except Exception:
            info = {'shortName': symbol, 'symbol': symbol}
        if info is None or not info:
            info = {'shortName': symbol, 'symbol': symbol}
        progress_bar.progress(15)

        status_text.text("正在获取K线数据...")
        data = None
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(get_cached_stock_data, symbol, '1y', market)
                data = future.result(timeout=20)
        except Exception:
            data = None
        progress_bar.progress(50)

        if data is None or data.empty:
            st.error(f"未能获取到 {symbol} 的数据，请检查：\n1. 股票代码是否正确\n2. 市场选择是否正确\n3. 网络连接是否正常")
            progress_bar.empty()
            status_text.empty()
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

        if len(data) < 30:
            st.warning(f"{symbol} 数据不足（仅{len(data)}天），部分指标可能无法计算")

        status_text.text("正在获取实时行情...")
        progress_bar.progress(55)
        quote = None
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(get_cached_realtime_quote, symbol, market)
                quote = future.result(timeout=3)
        except Exception:
            quote = None

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
        progress_bar.progress(75)

        stock_name = symbol
        if isinstance(info, dict):
            stock_name = info.get('shortName') or info.get('longName') or symbol
        if stock_name == symbol and market == "CN":
            status_text.text("正在获取股票名称...")
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(fetcher.get_stock_name, symbol, market)
                    stock_name = future.result(timeout=5)
            except Exception:
                stock_name = symbol
        elif stock_name == symbol:
            stock_name = symbol
        progress_bar.progress(78)

        intraday_data = None
        if market == "CN":
            status_text.text("正在获取分时数据...")
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(get_cached_intraday_data, symbol, market)
                    intraday_data = future.result(timeout=5)
            except Exception:
                intraday_data = None
        progress_bar.progress(82)

        status_text.text("正在计算技术指标 (MACD/RSI/KDJ/BOLL/MA)...")
        data = TechnicalIndicators.calculate_all(data)
        progress_bar.progress(92)

        status_text.text("正在生成交易信号...")
        signals = TechnicalIndicators.get_signals(data)
        progress_bar.progress(97)

        if 'error' in signals:
            st.warning(f"指标计算问题：{signals['error']}")

        status_text.text("正在渲染图表...")
        progress_bar.progress(99)

        st.session_state.analyzed_data = data
        st.session_state.analyzed_signals = signals
        st.session_state.analyzed_quote = quote
        st.session_state.analyzed_stock_name = stock_name

        period_days = {'1wk': 7, '1mo': 30, '3mo': 90, '6mo': 180, '1y': 365, '2y': 730}
        cutoff = data.index[-1] - pd.Timedelta(days=period_days.get(period, 365))
        display_data = data[data.index >= cutoff] if len(data[data.index >= cutoff]) >= 10 else data

        _render_analysis_results(display_data, signals, quote, symbol, stock_name, market, period, intraday_data=intraday_data)

        progress_bar.empty()
        status_text.empty()

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
                period
            )

    # 锚点滚动
    if st.session_state.pop('scroll_to_results', False):
        st.components.v1.html("""
        <script>
            var el = parent.document.getElementById('analysis-results');
            if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
        </script>
        """, height=0)
