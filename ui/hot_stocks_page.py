"""涨跌排行页面 — A股/港股/美股涨跌幅榜"""
import concurrent.futures
import streamlit as st
import pandas as pd
from config import CACHE_TTL_HOT_STOCKS
from stock_recommendation import StockRecommender
from ui.loading import make_progress_reporter
from quality_monitor import build_hot_data_status


_HOT_SECTION_LABELS = {
    "gainers": "个股涨幅榜",
    "losers": "个股跌幅榜",
}


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
        }
        return _run_hot_tasks(tasks, max_workers=2, progress_callback=progress_callback)
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
    """并发获取涨跌排行数据，单个源失败不拖垮整页。"""
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
    market_label = {"CN": "A股", "HK": "港股", "US": "美股"}.get(market, market)
    percent = max(0, min(100, int(percent or 0)))
    container.info(f"正在刷新涨跌排行 · {market_label}｜{step or '正在获取数据'}｜{percent}%")


def hot_stocks_page():
    """涨跌排行页面"""
    st.markdown("# 涨跌排行")

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
            "正在刷新涨跌排行",
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
        st.session_state.hot_data_status = build_hot_data_status(data)
        progress.complete("完成")
        loading_panel.empty()
    else:
        data = st.session_state.get('hot_data')

    if not data:
        st.info("点击“获取数据”刷新个股涨幅榜和跌幅榜。")
        return

    status = st.session_state.get("hot_data_status") or build_hot_data_status(data)
    counts = status.get("counts") or {}
    st.caption(
        f"数据覆盖：共 {status.get('total_rows', 0)} 条；"
        + "；".join(f"{key} {value}" for key, value in counts.items())
        + f"；刷新检查 {status.get('checked_at', '--')}"
    )
    if status.get("missing"):
        missing_labels = [_HOT_SECTION_LABELS.get(key, key) for key in (status.get("missing") or [])]
        st.warning("部分榜单为空：" + "、".join(missing_labels))

    if market == "CN":
        gainers = data.get('gainers', [])
        losers = data.get('losers', [])

        st.caption("涨跌排行用于观察全市场个股涨跌幅，保留创业板、科创板、北交所；智能推荐和推荐计划才仅限对应策略股票池。")

        st.subheader("个股涨幅榜")
        df_gainers = pd.DataFrame(gainers)
        if not df_gainers.empty:
            df_gainers = df_gainers.rename(columns={
                '代码': 'Symbol', '名称': 'Name', '最新价': 'Price',
                '涨跌幅': 'Change%', '换手率': 'Turnover%', '所属板块': 'Sector',
            })
            st.dataframe(df_gainers, width="stretch")
        else:
            st.info("暂无涨幅榜数据")

        st.subheader("个股跌幅榜")
        df_losers = pd.DataFrame(losers)
        if not df_losers.empty:
            df_losers = df_losers.rename(columns={
                '代码': 'Symbol', '名称': 'Name', '最新价': 'Price',
                '涨跌幅': 'Change%', '换手率': 'Turnover%', '所属板块': 'Sector',
            })
            st.dataframe(df_losers, width="stretch")
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
            st.dataframe(df_hot, width="stretch")
        else:
            st.info("暂无热门股票数据")

        st.subheader("涨幅榜")
        df_gainers = pd.DataFrame(gainers)
        if not df_gainers.empty:
            st.dataframe(df_gainers, width="stretch")
        else:
            st.info("暂无涨幅榜数据")

        st.subheader("跌幅榜")
        df_losers = pd.DataFrame(losers)
        if not df_losers.empty:
            st.dataframe(df_losers, width="stretch")
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
            st.dataframe(df_hot, width="stretch")
        else:
            st.info("暂无热门股票数据")

        st.subheader("涨幅榜")
        df_gainers = pd.DataFrame(gainers)
        if not df_gainers.empty:
            st.dataframe(df_gainers, width="stretch")
        else:
            st.info("暂无涨幅榜数据")

        st.subheader("跌幅榜")
        df_losers = pd.DataFrame(losers)
        if not df_losers.empty:
            st.dataframe(df_losers, width="stretch")
        else:
            st.info("暂无跌幅榜数据")
