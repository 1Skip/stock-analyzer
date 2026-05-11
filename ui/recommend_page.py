"""智能推荐页面 — 短线/长线龙头股推荐"""
import html
import concurrent.futures
import streamlit as st
from stock_recommendation import StockRecommender


def display_recommendation_list(recommended, strategy_name):
    """显示推荐列表"""
    if not recommended:
        st.warning(f"暂无{strategy_name}推荐股票")
        st.info("可能原因：\n1. 数据获取失败（网络问题）\n2. 股票分析返回None（数据不足）\n3. 请检查日志输出")
        return

    st.success(f"{strategy_name}：为您推荐以下 {len(recommended)} 只股票")

    for i, stock in enumerate(recommended, 1):
        with st.container():
            change_pct = stock.get('change_pct', 0) or 0
            if change_pct > 0:
                arrow = "📈"
            elif change_pct < 0:
                arrow = "📉"
            else:
                arrow = "➡"
            st.markdown(f"""
            <div class="stock-card">
                <h4>#{i} {html.escape(str(stock['symbol']))} {html.escape(str(stock['name']))}</h4>
                <p><strong>综合评分:</strong> {stock['score']}/100 |
                <strong>建议:</strong> {html.escape(str(stock['rating']))} |
                <strong>当前价:</strong> {stock['latest_price']:.2f} {arrow}{change_pct:+.2f}%</p>
            </div>
            """, unsafe_allow_html=True)

            ind = stock["indicators"]
            sig = stock["signals"]
            cols = st.columns(4)
            with cols[0]:
                macd_hist = ind.get("macd_hist", 0)
                st.markdown(f'<p style="font-size:1.05rem;margin:0"><b>MACD:</b> 柱:{macd_hist:.2f} DIF:{ind["macd"]:.2f} DEA:{ind["macd_signal"]:.2f}</p>', unsafe_allow_html=True)
                st.markdown(f'<p style="font-size:0.95rem;margin:0;opacity:0.85">{html.escape(sig["macd"])}</p>', unsafe_allow_html=True)
            with cols[1]:
                rsi6 = ind.get("rsi_6", ind.get("rsi", 0))
                rsi12 = ind.get("rsi_12", 0)
                rsi24 = ind.get("rsi_24", 0)
                st.markdown(f'<p style="font-size:1.05rem;margin:0"><b>RSI:</b> 6:{rsi6:.2f} 12:{rsi12:.2f} 24:{rsi24:.2f}</p>', unsafe_allow_html=True)
                st.markdown(f'<p style="font-size:0.95rem;margin:0;opacity:0.85">{html.escape(sig["rsi"])}</p>', unsafe_allow_html=True)
            with cols[2]:
                st.markdown(f'<p style="font-size:1.05rem;margin:0"><b>KDJ:</b> K:{ind["kdj_k"]:.2f} D:{ind["kdj_d"]:.2f} J:{ind["kdj_j"]:.2f}</p>', unsafe_allow_html=True)
                st.markdown(f'<p style="font-size:0.95rem;margin:0;opacity:0.85">{html.escape(sig["kdj"])}</p>', unsafe_allow_html=True)
            with cols[3]:
                boll_up = ind.get("boll_upper", 0)
                boll_mid = ind.get("boll_mid", 0)
                boll_low = ind.get("boll_lower", 0)
                st.markdown(f'<p style="font-size:1.05rem;margin:0"><b>布林带:</b> UP:{boll_up:.2f} MID:{boll_mid:.2f} LOW:{boll_low:.2f}</p>', unsafe_allow_html=True)
                st.markdown(f'<p style="font-size:0.95rem;margin:0;opacity:0.85">{html.escape(sig["boll"])}</p>', unsafe_allow_html=True)

            st.divider()


def recommended_stocks_page():
    """推荐股票页面 - 短线/长线龙头股推荐"""

    if 'rec_sector' not in st.session_state:
        st.session_state.rec_sector = "全部"
    if 'rec_num_stocks' not in st.session_state:
        st.session_state.rec_num_stocks = 5
    if 'rec_strategy' not in st.session_state:
        st.session_state.rec_strategy = "短线"

    def on_sector_change():
        st.session_state.rec_sector = st.session_state.rec_sector_select
        st.session_state.rec_data_loaded = False

    def on_num_stocks_change():
        st.session_state.rec_num_stocks = st.session_state.rec_num_slider

    def on_strategy_change():
        st.session_state.rec_strategy = st.session_state.rec_strategy_radio
        st.session_state.rec_data_loaded = False

    strategy = st.session_state.rec_strategy
    sector = st.session_state.rec_sector
    num_stocks = st.session_state.rec_num_stocks

    st.markdown(f'<h1 class="main-header">龙头股推荐 — {strategy}</h1>', unsafe_allow_html=True)

    st.radio("策略选择", options=["短线", "长线"], index=0 if strategy == "短线" else 1,
             horizontal=True, key="rec_strategy_radio", on_change=on_strategy_change)

    if strategy == "短线":
        st.info("基于MACD、RSI、KDJ、布林带等技术指标，筛选各板块短线龙头股（侧重短期动量与波动率）")
    else:
        st.info("基于MA60趋势、MACD趋势等长线指标，筛选各板块长线龙头股（侧重中长期趋势与估值合理性）")

    sector_options = ["全部", "苹果概念", "特斯拉概念", "电力", "算力租赁"]
    sector_index = sector_options.index(st.session_state.rec_sector)
    sector = st.selectbox("选择板块", options=sector_options,
                         index=sector_index,
                         key="rec_sector_select",
                         on_change=on_sector_change)

    num_stocks = st.slider("推荐数量", min_value=3, max_value=8,
                          value=st.session_state.rec_num_stocks,
                          key="rec_num_slider",
                          on_change=on_num_stocks_change)

    sector = st.session_state.rec_sector
    num_stocks = st.session_state.rec_num_stocks

    if 'rec_data_loaded' not in st.session_state:
        st.session_state.rec_data_loaded = False

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("刷新数据", type="secondary"):
            st.session_state.rec_data_loaded = False
            st.success("数据已刷新")

    if st.button("生成推荐", type="primary") or not st.session_state.rec_data_loaded:
        with st.spinner(f"正在分析{sector}板块（{strategy}），请稍候..."):
            recommender = StockRecommender()
            if strategy == "短线":
                if sector == "全部":
                    recommended = recommender.get_short_term_recommendations(num_stocks)
                    title = "短线推荐"
                else:
                    recommended = recommender.get_sector_short_term_recommendations(sector, num_stocks)
                    title = f"{sector} 短线龙头股"
            else:
                if sector == "全部":
                    recommended = recommender.get_long_term_recommendations(num_stocks)
                    title = "长线推荐"
                else:
                    recommended = recommender.get_sector_long_term_recommendations(sector, num_stocks)
                    title = f"{sector} 长线龙头股"

            if recommended:
                try:
                    from data_fetcher import StockDataFetcher
                    fetcher = StockDataFetcher()
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(
                            fetcher.get_batch_realtime_quotes,
                            [s['symbol'] for s in recommended]
                        )
                        quotes = future.result(timeout=3)
                    for s in recommended:
                        if s['symbol'] in quotes:
                            s['latest_price'] = quotes[s['symbol']]['price']
                            s['change_pct'] = quotes[s['symbol']]['change_pct']
                except Exception:
                    pass

            display_recommendation_list(recommended, title)
            st.session_state.rec_data_loaded = True
