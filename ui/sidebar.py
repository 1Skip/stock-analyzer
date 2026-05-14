"""侧边栏组件 — 大盘温度、自选股列表、数据源选择"""
import html
import streamlit as st
from config import (
    INDEX_WATCHLIST,
    INDEX_CACHE_TTL,
)
from watchlist import (
    remove_from_watchlist,
    get_watchlist,
)
from ui.cached_data import quote_service


def _open_watchlist_stock_in_main(symbol, market, name=None):
    """打开自选股对应的个股分析主页面。"""
    st.session_state.analyze_symbol = symbol
    st.session_state.analyze_symbol_input = symbol
    st.session_state.analyze_market = market
    st.session_state.trigger_analysis = True
    st.session_state.scroll_to_results = True
    st.session_state.pending_main_page = "个股分析"
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

        st.caption("点击股票后，主页会自动显示对应个股分析；点右侧 × 可移除。")
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
