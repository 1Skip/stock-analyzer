"""热门板块页面 — 行业/概念排行 + 涨跌幅榜"""
import html
import concurrent.futures
import streamlit as st
import pandas as pd
from config import CACHE_TTL_HOT_STOCKS
from stock_recommendation import StockRecommender
from ui.loading import make_progress_reporter


@st.cache_data(ttl=CACHE_TTL_HOT_STOCKS, show_spinner=False)
def get_cached_hot_stocks(market):
    """缓存热门股票数据"""
    return fetch_hot_stocks(market)


def fetch_hot_stocks(market, progress_callback=None):
    """获取热门股票数据，可选输出真实阶段进度。"""
    recommender = StockRecommender()
    _emit_progress(progress_callback, "初始化数据源", 8, market=market)
    if market == "CN":
        tasks = {
            'gainers': lambda: recommender.get_top_gainers_cn(limit=10),
            'losers': lambda: recommender.get_top_losers_cn(limit=10),
            'sectors': lambda: recommender.get_hot_sectors_cn(limit=30),
            'concepts': lambda: recommender.get_hot_concepts_cn(limit=30),
        }
        return _run_hot_tasks(tasks, max_workers=5, progress_callback=progress_callback)
    elif market == "HK":
        _emit_progress(progress_callback, "获取热门港股", 30)
        hot = recommender.get_hot_stocks_hk(limit=20)
        _emit_progress(progress_callback, "整理涨跌幅榜", 70, hot=len(hot or []))
        return {
            'hot': hot,
            'gainers': recommender.get_top_gainers_hk(limit=10, hot_stocks=hot),
            'losers': recommender.get_top_losers_hk(limit=10, hot_stocks=hot)
        }
    else:
        _emit_progress(progress_callback, "获取热门美股", 30)
        hot = recommender.get_hot_stocks_us(limit=20)
        _emit_progress(progress_callback, "整理涨跌幅榜", 70, hot=len(hot or []))
        return {
            'hot': hot,
            'gainers': recommender.get_top_gainers_us(limit=10, hot_stocks=hot),
            'losers': recommender.get_top_losers_us(limit=10, hot_stocks=hot)
        }


def _emit_progress(progress_callback, stage, percent, **metrics):
    if not callable(progress_callback):
        return
    try:
        progress_callback(stage, percent, metrics)
    except Exception:
        pass


def _run_hot_tasks(tasks, max_workers=4, progress_callback=None):
    """并发获取热门板块数据，单个源失败不拖垮整页。"""
    results = {key: [] for key in tasks}
    total = len(tasks)
    completed = 0
    _emit_progress(progress_callback, "提交排行任务", 20, total=total)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(task): key for key, task in tasks.items()}
        for future in concurrent.futures.as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result() or []
            except Exception:
                results[key] = []
            completed += 1
            _emit_progress(
                progress_callback,
                "排行任务完成",
                20 + int(65 * completed / max(1, total)),
                done=completed,
                total=total,
                latest=key,
            )
    return results


def _render_hot_loading(container, market, step, percent):
    """渲染热门板块加载卡，避免页面空白等待。"""
    market_label = {"CN": "A股", "US": "美股", "HK": "港股"}.get(market, market)
    safe_step = html.escape(str(step or "正在获取热门板块"))
    percent = max(0, min(100, int(percent)))
    with container.container():
        st.markdown(
            f"""
            <div class="hot-loading-strip">
              <div class="hot-loading-main">
                <span class="hot-loading-dot"></span>
                <div class="hot-loading-copy">
                  <div class="hot-loading-title">\u6b63\u5728\u5237\u65b0\u70ed\u95e8\u677f\u5757 &middot; {html.escape(market_label)}</div>
                  <div class="hot-loading-step">{safe_step}</div>
                </div>
                <span class="hot-loading-percent">{percent}%</span>
              </div>
              <div class="hot-loading-bar">
                <div style="width:{percent}%"></div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def hot_stocks_page():
    """热门板块页面"""
    st.markdown('<h1 class="main-header">热门板块</h1>', unsafe_allow_html=True)

    if 'hot_market' not in st.session_state:
        st.session_state.hot_market = "CN"

    def on_hot_market_change():
        st.session_state.hot_market = st.session_state.hot_market_select
        st.session_state.hot_data_loaded = False
        st.session_state.hot_data = None

    market_index = ["CN", "US", "HK"].index(st.session_state.hot_market) if st.session_state.hot_market in ["CN", "US", "HK"] else 0
    market = st.selectbox("选择市场", options=["CN", "US", "HK"],
                         index=market_index,
                         format_func=lambda x: {"CN": "A股", "US": "美股", "HK": "港股"}[x],
                         key="hot_market_select",
                         on_change=on_hot_market_change)

    market = st.session_state.hot_market

    if 'hot_data_loaded' not in st.session_state:
        st.session_state.hot_data_loaded = False
    if 'hot_data' not in st.session_state:
        st.session_state.hot_data = None

    col1, col2 = st.columns([1, 4])
    with col1:
        button_label = "刷新数据" if st.session_state.hot_data_loaded else "获取数据"
        refresh_clicked = st.button(button_label, type="primary")

    if refresh_clicked:
        loading_panel = st.empty()
        market_label = {"CN": "A股", "US": "美股", "HK": "港股"}.get(market, market)
        progress = make_progress_reporter(
            loading_panel,
            "正在刷新热门板块",
            context=market_label,
        )
        progress.update("启动", 5)
        get_cached_hot_stocks.clear()
        data = fetch_hot_stocks(
            market,
            progress_callback=lambda stage, percent, metrics=None: progress.update(stage, percent, metrics),
        )
        progress.update("整理展示数据", 92)
        st.session_state.hot_data_loaded = True
        st.session_state.hot_data = data
        progress.complete("完成")
        loading_panel.empty()
    else:
        data = st.session_state.get('hot_data')

    if not data:
        st.info("点击“获取数据”刷新行业、概念与个股涨跌幅排行。")
        return

    if market == "CN":
        sectors = data.get('sectors', [])
        concepts = data.get('concepts', [])
        gainers = data.get('gainers', [])
        losers = data.get('losers', [])

        st.caption("热门板块与个股涨跌幅榜用于观察全市场热度，保留创业板、科创板、北交所；智能推荐和推荐股推送才仅限沪深主板。")

        st.subheader("行业板块排行")
        if sectors:
            df_sectors = pd.DataFrame(sectors)
            def color_change(val):
                if val > 0:
                    return 'color: #ff3b30'
                elif val < 0:
                    return 'color: #34c759'
                return ''
            df_styled = df_sectors.style.map(color_change, subset=['涨跌幅', '领涨股涨幅'])
            st.dataframe(df_styled, use_container_width=True, hide_index=True)
        else:
            st.info("暂无行业板块数据")

        st.subheader("概念板块排行")
        if concepts:
            df_concepts = pd.DataFrame(concepts)
            df_c_styled = df_concepts.style.map(color_change, subset=['涨跌幅', '领涨股涨幅'])
            st.dataframe(df_c_styled, use_container_width=True, hide_index=True)
        else:
            st.info("暂无概念板块数据")

        st.subheader("个股涨幅榜")
        df_gainers = pd.DataFrame(gainers)
        if not df_gainers.empty:
            df_gainers = df_gainers.rename(columns={
                '代码': 'Symbol', '名称': 'Name', '最新价': 'Price',
                '涨跌幅': 'Change%', '换手率': 'Turnover%', '所属板块': 'Sector',
            })
            st.dataframe(df_gainers, use_container_width=True)
        else:
            st.info("暂无涨幅榜数据")

        st.subheader("个股跌幅榜")
        df_losers = pd.DataFrame(losers)
        if not df_losers.empty:
            df_losers = df_losers.rename(columns={
                '代码': 'Symbol', '名称': 'Name', '最新价': 'Price',
                '涨跌幅': 'Change%', '换手率': 'Turnover%', '所属板块': 'Sector',
            })
            st.dataframe(df_losers, use_container_width=True)
        else:
            st.info("暂无跌幅榜数据")

    elif market == "HK":
        hot = data.get('hot', [])
        gainers = data.get('gainers', [])
        losers = data.get('losers', [])

        if not hot:
            st.warning("暂无港股热门数据，请稍后重试")
            return

        st.subheader("热门股票")
        df_hot = pd.DataFrame(hot)
        if not df_hot.empty:
            df_hot = df_hot.rename(columns={
                '代码': 'Symbol', '名称': 'Name', '最新价': 'Price',
                '涨跌幅': 'Change%', '换手率': 'Turnover%',
                '成交量': 'Volume', '成交额': 'Amount', '热度分数': 'Score'
            })
            st.dataframe(df_hot, use_container_width=True)
        else:
            st.info("暂无热门股票数据")

        st.subheader("涨幅榜")
        df_gainers = pd.DataFrame(gainers)
        if not df_gainers.empty:
            st.dataframe(df_gainers, use_container_width=True)
        else:
            st.info("暂无涨幅榜数据")

        st.subheader("跌幅榜")
        df_losers = pd.DataFrame(losers)
        if not df_losers.empty:
            st.dataframe(df_losers, use_container_width=True)
        else:
            st.info("暂无跌幅榜数据")

    else:
        hot = data.get('hot', [])
        gainers = data.get('gainers', [])
        losers = data.get('losers', [])

        if not hot:
            st.warning("暂无美股热门数据，请稍后重试")
            return

        st.subheader("美股热门")
        df_hot = pd.DataFrame(hot)
        if not df_hot.empty:
            st.dataframe(df_hot, use_container_width=True)
        else:
            st.info("暂无热门股票数据")

        st.subheader("涨幅榜")
        df_gainers = pd.DataFrame(gainers)
        if not df_gainers.empty:
            st.dataframe(df_gainers, use_container_width=True)
        else:
            st.info("暂无涨幅榜数据")

        st.subheader("跌幅榜")
        df_losers = pd.DataFrame(losers)
        if not df_losers.empty:
            st.dataframe(df_losers, use_container_width=True)
        else:
            st.info("暂无跌幅榜数据")
