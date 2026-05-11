"""热门板块页面 — 行业/概念排行 + 涨跌幅榜"""
import streamlit as st
import pandas as pd
from config import CACHE_TTL_HOT_STOCKS
from stock_recommendation import StockRecommender


@st.cache_data(ttl=CACHE_TTL_HOT_STOCKS, show_spinner=False)
def get_cached_hot_stocks(market):
    """缓存热门股票数据"""
    recommender = StockRecommender()
    if market == "CN":
        return {
            'hot': recommender.get_hot_stocks_cn(limit=20),
            'gainers': recommender.get_top_gainers_cn(limit=10),
            'losers': recommender.get_top_losers_cn(limit=10),
            'sectors': recommender.get_hot_sectors_cn(limit=30),
            'concepts': recommender.get_hot_concepts_cn(limit=30)
        }
    elif market == "HK":
        hot = recommender.get_hot_stocks_hk(limit=20)
        return {
            'hot': hot,
            'gainers': recommender.get_top_gainers_hk(limit=10, hot_stocks=hot),
            'losers': recommender.get_top_losers_hk(limit=10, hot_stocks=hot)
        }
    else:
        hot = recommender.get_hot_stocks_us(limit=20)
        return {
            'hot': hot,
            'gainers': recommender.get_top_gainers_us(limit=10, hot_stocks=hot),
            'losers': recommender.get_top_losers_us(limit=10, hot_stocks=hot)
        }


def hot_stocks_page():
    """热门板块页面"""
    st.markdown('<h1 class="main-header">热门板块</h1>', unsafe_allow_html=True)

    if 'hot_market' not in st.session_state:
        st.session_state.hot_market = "CN"

    def on_hot_market_change():
        st.session_state.hot_market = st.session_state.hot_market_select
        st.session_state.hot_data_loaded = False

    market_index = ["CN", "US", "HK"].index(st.session_state.hot_market) if st.session_state.hot_market in ["CN", "US", "HK"] else 0
    market = st.selectbox("选择市场", options=["CN", "US", "HK"],
                         index=market_index,
                         format_func=lambda x: {"CN": "A股", "US": "美股", "HK": "港股"}[x],
                         key="hot_market_select",
                         on_change=on_hot_market_change)

    market = st.session_state.hot_market

    if 'hot_data_loaded' not in st.session_state:
        st.session_state.hot_data_loaded = False

    col1, col2 = st.columns([1, 4])
    with col1:
        refresh_clicked = st.button("刷新数据", type="primary")

    if refresh_clicked or not st.session_state.hot_data_loaded:
        with st.spinner("正在获取热门板块..."):
            get_cached_hot_stocks.clear()
            data = get_cached_hot_stocks(market)
            st.session_state.hot_data_loaded = True
            st.session_state.hot_data = data
    else:
        data = st.session_state.get('hot_data')

    if data:
        if market == "CN":
            sectors = data.get('sectors', [])
            concepts = data.get('concepts', [])
            gainers = data.get('gainers', [])
            losers = data.get('losers', [])

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
