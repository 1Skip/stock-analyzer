"""侧边栏组件 — 大盘温度、自选股列表、mini 分析面板、数据源选择"""
import json as _json_for_hash
import html
import streamlit as st
from config import (
    MARKET_INDEX_ENABLED,
    INDEX_WATCHLIST,
    INDEX_CACHE_TTL,
    CACHE_TTL_WATCHLIST_SUMMARY,
    CACHE_TTL_WATCHLIST_MINI,
)
from watchlist import (
    add_to_watchlist, remove_from_watchlist,
    get_watchlist, is_in_watchlist, get_watchlist_summary,
)
from chart_utils import classify_signal
from ui.cached_data import quote_service


def display_market_temperature():
    """侧边栏大盘温度卡片 — 上证/深证/创业板实时涨跌"""

    @st.cache_data(ttl=INDEX_CACHE_TTL, show_spinner=False)
    def _fetch_indices():
        results = []
        for code, name in INDEX_WATCHLIST:
            quote = quote_service.get_index_realtime(code)
            if quote:
                results.append(quote)
        return results

    indices = _fetch_indices()
    if not indices:
        return

    rows = []
    for idx in indices:
        pct = idx['change_pct']
        direction = "🟢" if pct > 0 else ("🔴" if pct < 0 else "⚪")
        color = "var(--color-rise)" if pct >= 0 else "var(--color-fall)"
        rows.append(
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:3px 0;font-size:0.92rem">'
            f'<span style="opacity:0.85">{html.escape(str(idx["name"]))}</span>'
            f'<span><b>{idx["price"]:.2f}</b> '
            f'<span style="color:{color}">{direction} {pct:+.2f}%</span></span>'
            f'</div>'
        )

    st.markdown(
        f'<div style="margin:12px 0;padding:10px 12px;border-radius:10px;'
        f'background:rgba(128,128,128,0.06)">'
        f'<div style="font-size:0.8rem;opacity:0.6;margin-bottom:6px">大盘温度</div>'
        f'{"".join(rows)}'
        f'</div>',
        unsafe_allow_html=True
    )


@st.cache_data(ttl=CACHE_TTL_WATCHLIST_SUMMARY, show_spinner=False)
def _cached_watchlist_summary(_watchlist_hash):
    """获取自选股技术摘要（带缓存，5分钟有效）"""
    watchlist = get_watchlist()
    if not watchlist:
        return []
    return get_watchlist_summary(watchlist)


def display_watchlist_sidebar():
    """在侧边栏显示自选股列表 — 含实时信号和入场提示"""
    watchlist = get_watchlist()

    with st.expander("自选股"):
        if not watchlist:
            st.caption("暂无自选股")
            return None

        watchlist_hash = _json_for_hash.dumps(
            [(item['symbol'], item['market']) for item in watchlist],
            sort_keys=True
        )

        with st.spinner(""):
            summaries = _cached_watchlist_summary(watchlist_hash)

        if not summaries:
            for item in watchlist:
                col1, col2 = st.columns([4, 1])
                with col1:
                    display_text = f"{item['symbol']}"
                    if item['name'] and item['name'] != item['symbol']:
                        display_text += f" · {item['name'][:4]}"
                    if st.button(display_text, key=f"wl_{item['symbol']}_{item['market']}", use_container_width=True):
                        st.session_state.wl_view_symbol = item['symbol']
                        st.session_state.wl_view_market = item['market']
                with col2:
                    if st.button("✕", key=f"del_{item['symbol']}_{item['market']}", help="移除"):
                        remove_from_watchlist(item['symbol'], item['market'])
                        st.rerun()
            return None

        for i, item in enumerate(summaries):
            symbol = item['symbol']
            name = item.get('name', symbol)
            market = item.get('market', 'CN')
            error = item.get('error')

            with st.container(border=True):
                col_title, col_price, col_del = st.columns([2.5, 2, 0.8])
                with col_title:
                    st.markdown(f'<span style="font-weight:600">{html.escape(symbol)}</span> · {html.escape(name[:6])}',
                               unsafe_allow_html=True)
                with col_price:
                    if item['price'] is not None:
                        change = item.get('change_pct', 0) or 0
                        color = "#ff3b30" if change >= 0 else "#34c759"
                        arrow = "+" if change >= 0 else ""
                        st.markdown(f'<span style="color:{color};font-weight:600">{arrow}{change:.2f}%</span> '
                                   f'<span style="font-size:0.85rem">¥{item["price"]:.2f}</span>',
                                   unsafe_allow_html=True)

                with col_del:
                    if st.button("✕", key=f"wldel_{symbol}_{market}_{i}", help="移除"):
                        remove_from_watchlist(symbol, market)
                        st.rerun()

                if error:
                    st.caption(f"⚠ {error}")
                else:
                    signal_text = item.get('signal_summary', '--')
                    hint_text = item.get('entry_hint', '--')

                    cls = classify_signal(signal_text)

                    st.markdown(
                        f'<span class="signal-badge {cls}" style="font-size:0.75rem">{html.escape(str(signal_text))}</span> '
                        f'<span style="font-size:0.75rem;color:var(--text-color-secondary)">{html.escape(str(hint_text))}</span>',
                        unsafe_allow_html=True
                    )

                if st.button("查看分析", key=f"wlview_{symbol}_{market}_{i}", use_container_width=True):
                    st.session_state.wl_view_symbol = symbol
                    st.session_state.wl_view_market = market

    return summaries


@st.cache_data(ttl=CACHE_TTL_WATCHLIST_MINI, show_spinner=False)
def _cached_mini_analysis(symbol, market):
    """获取单只股票简要分析数据（侧边栏 mini 面板用，5分钟缓存）"""
    from watchlist import get_watchlist_summary
    results = get_watchlist_summary([{'symbol': symbol, 'name': symbol, 'market': market}])
    return results[0] if results else None


def display_watchlist_mini_panel(summaries):
    """在侧边栏显示选中自选股的 mini 分析面板"""
    symbol = st.session_state.get('wl_view_symbol')
    market = st.session_state.get('wl_view_market')

    if not symbol:
        return

    result = None
    if summaries:
        for s in summaries:
            if s['symbol'] == symbol and s['market'] == market:
                result = s
                break

    if result is None:
        result = _cached_mini_analysis(symbol, market)

    if result is None:
        return

    error = result.get('error')
    price = result.get('price')
    change_pct = result.get('change_pct', 0) or 0
    signal_text = result.get('signal_summary', '--')
    hint_text = result.get('entry_hint', '--')
    indicators = result.get('indicators', {})
    name = result.get('name', symbol)

    col_close = st.columns([6, 1])
    with col_close[1]:
        if st.button("✕", key="wl_mini_close", help="关闭"):
            st.session_state.wl_view_symbol = None
            st.session_state.wl_view_market = None
            st.rerun()

    with st.container(border=True):
        if error:
            st.caption(f"⚠ {error}")
            return

        change_color = "#ff3b30" if change_pct >= 0 else "#34c759"
        arrow_sign = "+" if change_pct >= 0 else ""
        st.markdown(
            f'<span style="font-weight:600">{html.escape(symbol)}</span> · {html.escape(name[:6])}'
            f'&nbsp;&nbsp;<span style="color:{change_color};font-weight:600">¥{price:.2f} {arrow_sign}{change_pct:.2f}%</span>',
            unsafe_allow_html=True
        )

        st.divider()

        cls = classify_signal(signal_text)

        st.markdown(
            f'<span class="signal-badge {cls}" style="font-size:0.75rem">{html.escape(str(signal_text))}</span>',
            unsafe_allow_html=True
        )

        ind_lines = []
        rsi = indicators.get('rsi')
        if rsi is not None:
            ind_lines.append(f"RSI: {rsi:.1f}")

        macd = indicators.get('macd')
        macd_signal = indicators.get('macd_signal')
        if macd is not None and macd_signal is not None:
            macd_status = "金叉" if macd > macd_signal else "死叉"
            ind_lines.append(f"MACD: {macd_status}")

        k, d, j = indicators.get('kdj_k'), indicators.get('kdj_d'), indicators.get('kdj_j')
        if k is not None and d is not None and j is not None:
            ind_lines.append(f"KDJ: K{k:.1f} D{d:.1f} J{j:.1f}")

        boll_upper = indicators.get('boll_upper')
        boll_lower = indicators.get('boll_lower')
        boll_mid = indicators.get('boll_mid')
        if boll_upper is not None and boll_lower is not None and price is not None:
            band_range = boll_upper - boll_lower
            if band_range > 0:
                pos = (price - boll_lower) / band_range
                if pos <= 0.05:
                    boll_pos = "下轨附近"
                elif pos <= 0.35:
                    boll_pos = "偏下区间"
                elif pos <= 0.65:
                    boll_pos = "中轨附近"
                elif pos <= 0.95:
                    boll_pos = "偏上区间"
                else:
                    boll_pos = "上轨附近"
                ind_lines.append(f"布林: {boll_pos}")

        if ind_lines:
            st.caption("  |  ".join(ind_lines))

        if hint_text and hint_text != '--':
            st.caption(f"入场: {hint_text}")

        if st.button("在主页查看完整分析 →", key="wl_mini_full", use_container_width=True):
            st.session_state.analyze_symbol = symbol
            st.session_state.analyze_market = market
            st.session_state.trigger_analysis = True
            st.session_state.scroll_to_results = True
            st.session_state.wl_view_symbol = None
            st.session_state.wl_view_market = None
            st.rerun()


def display_data_source_selector():
    """数据源设置（含简要说明）"""
    with st.expander("数据源"):
        current_source = quote_service.get_preferred_source()

        source_options = {
            'auto': '自动选择（推荐）',
            'akshare': 'AKShare（腾讯财经）',
            'sina': '新浪财经',
        }

        selected = st.selectbox(
            "优先数据源（A股）",
            options=list(source_options.keys()),
            index=list(source_options.keys()).index(current_source) if current_source in source_options else 0,
            format_func=lambda x: source_options[x]
        )

        if selected != current_source:
            quote_service.set_preferred_source(selected)
            st.success(f"已切换到: {source_options[selected]}")
            st.info("请重新获取数据以生效")

        with st.expander("查看详情"):
            st.markdown("""
            **A股** — AKShare（腾讯财经）→ 新浪财经 → 离线缓存

            **美股** — 新浪财经（实时 + 日K）

            **港股** — 新浪（实时）+ Yahoo（日K）

            实时行情延迟 3~5 秒，历史日K收盘后更新
            """)
