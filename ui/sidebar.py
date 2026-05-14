"""侧边栏组件 — 大盘温度、自选股列表、mini 分析面板、数据源选择"""
import html
import streamlit as st
from config import (
    INDEX_WATCHLIST,
    INDEX_CACHE_TTL,
    CACHE_TTL_WATCHLIST_MINI,
)
from watchlist import (
    remove_from_watchlist,
    get_watchlist, get_watchlist_summary,
)
from chart_utils import classify_signal
from ui.cached_data import quote_service


def _open_watchlist_stock_in_main(symbol, market, name=None):
    """打开自选股对应的个股分析主页面。"""
    st.session_state.analyze_symbol = symbol
    st.session_state.analyze_symbol_input = symbol
    st.session_state.analyze_market = market
    st.session_state.trigger_analysis = True
    st.session_state.scroll_to_results = True
    st.session_state.pending_main_page = "个股分析"
    st.session_state.wl_view_symbol = symbol
    st.session_state.wl_view_market = market
    st.session_state.quick_match_caption = f"已从自选股打开：{name or symbol} ({symbol})"


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


def display_watchlist_sidebar():
    """在侧边栏常驻显示自选股轻量列表。"""
    watchlist = get_watchlist()

    with st.expander(f"自选股（{len(watchlist)}）"):
        if not watchlist:
            st.caption("暂无自选股")
            return

        st.caption("点击股票查看下方详情，点右侧 × 可移除。")
        for index, raw_item in enumerate(watchlist):
            symbol = raw_item.get('symbol', '')
            name = raw_item.get('name') or symbol
            market = raw_item.get('market', 'CN')
            row = st.columns([4.6, 0.9], gap="small")
            with row[0]:
                label = f"{symbol} · {name[:6]}" if name and name != symbol else symbol
                if st.button(label, key=f"wl_pick_{symbol}_{market}_{index}", use_container_width=True):
                    _open_watchlist_stock_in_main(symbol, market, name)
                    st.rerun()
            with row[1]:
                if st.button("×", key=f"wl_remove_{symbol}_{market}_{index}", help="移除自选", use_container_width=True):
                    remove_from_watchlist(symbol, market)
                    st.rerun()



@st.cache_data(ttl=CACHE_TTL_WATCHLIST_MINI, show_spinner=False)
def _cached_mini_analysis(symbol, market):
    """获取单只股票简要分析数据（侧边栏 mini 面板用，5分钟缓存）"""
    from watchlist import get_watchlist_summary
    results = get_watchlist_summary([{'symbol': symbol, 'name': symbol, 'market': market}])
    return results[0] if results else None


def display_watchlist_mini_panel():
    """在侧边栏显示选中自选股的 mini 分析面板"""
    symbol = st.session_state.get('wl_view_symbol')
    market = st.session_state.get('wl_view_market')

    if not symbol:
        return

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

    st.caption("自选详情")

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
            _open_watchlist_stock_in_main(symbol, market, name)
            st.rerun()


def display_data_source_selector():
    """数据源设置（含当前分层说明）。"""
    with st.expander("数据源"):
        current_source = quote_service.get_preferred_source()

        source_options = {
            'auto': '自动选择（推荐）',
            'akshare_em': '东方财富（A股历史行情）',
            'akshare': '腾讯财经（A股备选行情）',
            'sina': '新浪财经（A股/美股实时兜底）',
        }

        selected = st.selectbox(
            "A股行情优先源",
            options=list(source_options.keys()),
            index=list(source_options.keys()).index(current_source) if current_source in source_options else 0,
            format_func=lambda x: source_options[x]
        )

        if selected != current_source:
            quote_service.set_preferred_source(selected)
            st.success(f"已切换到: {source_options[selected]}")
            st.info("请重新获取数据以生效")

        with st.expander("查看详情"):
            st.markdown(
                """
                **A股行情优先源** — 上面的选择框只影响 A股历史K线/行情 获取顺序：东方财富 → 腾讯财经 → 新浪财经 → Yahoo Finance → 离线缓存。

                **其他模块自动使用** — 热门板块/排行走同花顺行业/概念/全市场涨跌幅优先，新浪财经作为个股排行兜底；港股/美股仍按模块自动使用 Yahoo 和新浪。

                **个股扩展信息** — AKShare 聚合东方财富/同花顺/巨潮等接口，覆盖财务摘要、资金流、新闻、研报、EPS 一致预期、龙虎榜、限售解禁、公告、行业/概念归因。

                **基础资料/估值** — AKShare/东方财富为主，腾讯行情补充 PE、PB、换手率、市值等字段，巨潮补充公司行业和上市信息。

                **名称搜索** — 本地股票名称索引 + 缓存快照，避免每次输入名称都请求远程接口。

                实时行情通常存在 3~5 秒延迟，盘后和非交易时段以数据源最近更新时间为准。
                """
            )
