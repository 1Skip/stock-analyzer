"""
股票分析系统 - Web版本 (优化版)
使用Streamlit构建，带缓存加速
"""
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time

# 导入原有模块
from data_fetcher import StockDataFetcher, CN_STOCK_NAMES_EXTENDED
from technical_indicators import TechnicalIndicators
from stock_recommendation import StockRecommender
from watchlist import add_to_watchlist, remove_from_watchlist, get_watchlist, is_in_watchlist

# 初始化缓存数据获取器
fetcher = StockDataFetcher()

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_stock_data(symbol, period, market):
    """缓存股票数据获取"""
    try:
        return fetcher.get_stock_data(symbol, period=period, market=market)
    except Exception as e:
        return None

@st.cache_data(ttl=60, show_spinner=False)
def get_cached_stock_info(symbol, market):
    """缓存股票基本信息"""
    try:
        return fetcher.get_stock_info(symbol, market)
    except Exception as e:
        return {}

@st.cache_data(ttl=60, show_spinner=False)
def get_cached_realtime_quote(symbol, market):
    """缓存实时行情"""
    try:
        return fetcher.get_realtime_quote(symbol, market)
    except Exception as e:
        return None

# 页面配置
st.set_page_config(
    page_title="股票分析系统",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义CSS样式
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    .buy-signal {
        color: #e74c3c;
        font-weight: bold;
    }
    .sell-signal {
        color: #27ae60;
        font-weight: bold;
    }
    .neutral-signal {
        color: #7f8c8d;
    }
    .stock-card {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .watchlist-item {
        background-color: #f8f9fa;
        border-radius: 5px;
        padding: 0.5rem;
        margin: 0.25rem 0;
        border-left: 3px solid #1f77b4;
    }
    .stButton button {
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

def plot_candlestick_chart(data, title="K线图"):
    """使用Plotly绘制K线图"""
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.6, 0.2, 0.2],
        subplot_titles=('价格', '成交量', 'MACD')
    )

    # K线图
    fig.add_trace(
        go.Candlestick(
            x=data.index,
            open=data['open'],
            high=data['high'],
            low=data['low'],
            close=data['close'],
            name='K线',
            increasing_line_color='#e74c3c',
            decreasing_line_color='#27ae60'
        ),
        row=1, col=1
    )

    # 移动平均线
    if 'ma5' in data.columns:
        fig.add_trace(go.Scatter(x=data.index, y=data['ma5'], name='MA5', line=dict(color='orange')), row=1, col=1)
    if 'ma20' in data.columns:
        fig.add_trace(go.Scatter(x=data.index, y=data['ma20'], name='MA20', line=dict(color='blue')), row=1, col=1)
    if 'ma60' in data.columns:
        fig.add_trace(go.Scatter(x=data.index, y=data['ma60'], name='MA60', line=dict(color='purple')), row=1, col=1)

    # 成交量
    if 'volume' in data.columns:
        colors = ['#e74c3c' if data['close'].iloc[i] >= data['open'].iloc[i] else '#27ae60'
                  for i in range(len(data))]
        fig.add_trace(
            go.Bar(x=data.index, y=data['volume'], name='成交量', marker_color=colors),
            row=2, col=1
        )

    # MACD
    if 'macd' in data.columns:
        fig.add_trace(go.Scatter(x=data.index, y=data['macd'], name='MACD', line=dict(color='blue')), row=3, col=1)
        fig.add_trace(go.Scatter(x=data.index, y=data['macd_signal'], name='Signal', line=dict(color='red')), row=3, col=1)

        # MACD柱状图
        colors_macd = ['#e74c3c' if v >= 0 else '#27ae60' for v in data['macd_hist']]
        fig.add_trace(
            go.Bar(x=data.index, y=data['macd_hist'], name='MACD Hist', marker_color=colors_macd),
            row=3, col=1
        )

    fig.update_layout(
        title=title,
        xaxis_rangeslider_visible=False,
        height=800,
        showlegend=True,
        hovermode='x unified'
    )

    fig.update_xaxes(rangeslider_visible=False)
    fig.update_yaxes(title_text="价格", row=1, col=1)
    fig.update_yaxes(title_text="成交量", row=2, col=1)
    fig.update_yaxes(title_text="MACD", row=3, col=1)

    return fig

def plot_rsi_chart(data):
    """绘制RSI图表"""
    fig = go.Figure()

    fig.add_trace(go.Scatter(x=data.index, y=data['rsi'], name='RSI(14)', line=dict(color='purple', width=2)))
    fig.add_hline(y=70, line_dash="dash", line_color="red", annotation_text="超买(70)")
    fig.add_hline(y=30, line_dash="dash", line_color="green", annotation_text="超卖(30)")

    fig.update_layout(
        title="RSI指标 (相对强弱指数)",
        height=400,
        yaxis_range=[0, 100],
        hovermode='x unified'
    )

    return fig

def plot_kdj_chart(data):
    """绘制KDJ图表"""
    fig = go.Figure()

    fig.add_trace(go.Scatter(x=data.index, y=data['kdj_k'], name='K', line=dict(color='blue')))
    fig.add_trace(go.Scatter(x=data.index, y=data['kdj_d'], name='D', line=dict(color='orange')))
    fig.add_trace(go.Scatter(x=data.index, y=data['kdj_j'], name='J', line=dict(color='purple')))
    fig.add_hline(y=80, line_dash="dash", line_color="red")
    fig.add_hline(y=20, line_dash="dash", line_color="green")

    fig.update_layout(
        title="KDJ指标 (随机指标)",
        height=400,
        hovermode='x unified'
    )

    return fig

def plot_boll_chart(data):
    """绘制布林带图表"""
    fig = go.Figure()

    fig.add_trace(go.Scatter(x=data.index, y=data['close'], name='价格', line=dict(color='black', width=2)))
    fig.add_trace(go.Scatter(x=data.index, y=data['boll_upper'], name='上轨', line=dict(color='red')))
    fig.add_trace(go.Scatter(x=data.index, y=data['boll_mid'], name='中轨', line=dict(color='blue')))
    fig.add_trace(go.Scatter(x=data.index, y=data['boll_lower'], name='下轨', line=dict(color='green')))

    # 填充布林带区域
    fig.add_trace(go.Scatter(
        x=data.index.tolist() + data.index.tolist()[::-1],
        y=data['boll_upper'].tolist() + data['boll_lower'].tolist()[::-1],
        fill='toself',
        fillcolor='rgba(0,100,80,0.1)',
        line=dict(color='rgba(255,255,255,0)'),
        name='布林带区间'
    ))

    fig.update_layout(
        title="布林带 (BOLL)",
        height=400,
        hovermode='x unified'
    )

    return fig

def display_signals(signals):
    """显示交易信号"""
    # 处理错误情况
    if 'error' in signals:
        st.warning(f"⚠️ {signals['error']}")
        return

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.subheader("MACD")
        macd_signal = signals.get('macd', '暂无数据')
        if "金叉" in macd_signal:
            st.markdown(f"<span class='buy-signal'>📈 {macd_signal}</span>", unsafe_allow_html=True)
        elif "死叉" in macd_signal:
            st.markdown(f"<span class='sell-signal'>📉 {macd_signal}</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span class='neutral-signal'>➖ {macd_signal}</span>", unsafe_allow_html=True)

    with col2:
        st.subheader("RSI")
        rsi_signal = signals.get('rsi', '暂无数据')
        if "超卖" in rsi_signal:
            st.markdown(f"<span class='buy-signal'>🔵 {rsi_signal}</span>", unsafe_allow_html=True)
        elif "超买" in rsi_signal:
            st.markdown(f"<span class='sell-signal'>🔴 {rsi_signal}</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span class='neutral-signal'>⚪ {rsi_signal}</span>", unsafe_allow_html=True)

    with col3:
        st.subheader("KDJ")
        kdj_signal = signals.get('kdj', '暂无数据')
        if "买入" in kdj_signal or "超卖" in kdj_signal:
            st.markdown(f"<span class='buy-signal'>📈 {kdj_signal}</span>", unsafe_allow_html=True)
        elif "卖出" in kdj_signal or "超买" in kdj_signal:
            st.markdown(f"<span class='sell-signal'>📉 {kdj_signal}</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span class='neutral-signal'>➖ {kdj_signal}</span>", unsafe_allow_html=True)

    with col4:
        st.subheader("布林带")
        boll_signal = signals.get('boll', '暂无数据')
        if "反弹" in boll_signal or "偏多" in boll_signal:
            st.markdown(f"<span class='buy-signal'>📈 {boll_signal}</span>", unsafe_allow_html=True)
        elif "回调" in boll_signal or "偏空" in boll_signal:
            st.markdown(f"<span class='sell-signal'>📉 {boll_signal}</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span class='neutral-signal'>➖ {boll_signal}</span>", unsafe_allow_html=True)

    # 综合建议
    st.divider()
    recommendation = signals.get('recommendation', '观望')
    if "买入" in recommendation:
        st.success(f"### 💡 综合建议: {recommendation}")
    elif "卖出" in recommendation:
        st.error(f"### 💡 综合建议: {recommendation}")
    else:
        st.info(f"### 💡 综合建议: {recommendation}")

def analyze_stock_page():
    """个股分析页面"""
    st.markdown('<h1 class="main-header">📊 股票技术分析</h1>', unsafe_allow_html=True)

    # 使用 session state 保存查询状态 - 初始化
    if 'analyze_symbol' not in st.session_state:
        st.session_state.analyze_symbol = "000001"
    if 'analyze_market' not in st.session_state:
        st.session_state.analyze_market = "CN"
    if 'analyze_period' not in st.session_state:
        st.session_state.analyze_period = "3mo"

    # 回调函数用于保存状态
    def on_symbol_change():
        st.session_state.analyze_symbol = st.session_state.analyze_symbol_input

    def on_market_change():
        st.session_state.analyze_market = st.session_state.analyze_market_select

    def on_period_change():
        st.session_state.analyze_period = st.session_state.analyze_period_select

    # 输入区域
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
        # 默认使用3个月数据，加载更快
        period_index = ["1mo", "3mo", "6mo", "1y"].index(st.session_state.analyze_period)
        period = st.selectbox("时间周期", options=["1mo", "3mo", "6mo", "1y"],
                             index=period_index,
                             key="analyze_period_select",
                             on_change=on_period_change)

    # 从 session state 读取当前值
    symbol = st.session_state.analyze_symbol
    market = st.session_state.analyze_market
    period = st.session_state.analyze_period

    if st.button("🔍 开始分析", type="primary", use_container_width=True):

        # 使用进度条显示加载状态
        progress_bar = st.progress(0)
        status_text = st.empty()

        status_text.text("⏳ 正在获取股票信息...")
        progress_bar.progress(10)

        # 并行获取基本信息和实时行情
        info = get_cached_stock_info(symbol, market)
        progress_bar.progress(30)

        status_text.text("⏳ 正在获取实时行情...")
        quote = get_cached_realtime_quote(symbol, market)
        progress_bar.progress(50)

        status_text.text("⏳ 正在获取历史数据...")
        data = get_cached_stock_data(symbol, period, market)
        progress_bar.progress(70)

        if data is None or data.empty:
            st.error(f"❌ 未能获取到 {symbol} 的数据，请检查：\n1. 股票代码是否正确\n2. 市场选择是否正确\n3. 网络连接是否正常")
            progress_bar.empty()
            status_text.empty()
            return

        # 检查数据是否足够（至少需要30天数据）
        if len(data) < 30:
            st.warning(f"⚠️ {symbol} 数据不足（仅{len(data)}天），部分指标可能无法计算")

        status_text.text("⏳ 正在计算技术指标...")
        # 计算指标
        data = TechnicalIndicators.calculate_all(data)
        signals = TechnicalIndicators.get_signals(data)
        progress_bar.progress(100)

        # 检查是否有错误
        if 'error' in signals:
            st.warning(f"⚠️ 指标计算问题：{signals['error']}")

        # 清除进度条
        progress_bar.empty()
        status_text.empty()

        # 显示基本信息
        st.divider()

        # 股票标题 - 使用增强的get_stock_name方法
        stock_name = fetcher.get_stock_name(symbol, market)

        # 标题和自选股按钮并排
        col_title, col_watchlist = st.columns([3, 1])
        with col_title:
            st.header(f"{symbol} {stock_name}")
        with col_watchlist:
            # 自选股按钮
            if is_in_watchlist(symbol, market):
                if st.button("❌ 移除自选", key="remove_watchlist"):
                    success, msg = remove_from_watchlist(symbol, market)
                    if success:
                        st.success(msg)
                        st.rerun()
            else:
                if st.button("⭐ 加入自选", key="add_watchlist"):
                    success, msg = add_to_watchlist(symbol, stock_name, market)
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.warning(msg)

        # 实时行情卡片
        if quote:
            cols = st.columns(5)
            with cols[0]:
                st.metric("最新价", f"{quote['price']:.2f}", f"{quote['change']:.2f}%")
            with cols[1]:
                st.metric("最高", f"{quote['high']:.2f}")
            with cols[2]:
                st.metric("最低", f"{quote['low']:.2f}")
            with cols[3]:
                volume = quote['volume'] / 10000 if quote['volume'] > 10000 else quote['volume']
                unit = "万" if quote['volume'] > 10000 else ""
                st.metric("成交量", f"{volume:.0f}{unit}")
            with cols[4]:
                st.metric("今开", f"{quote['open']:.2f}")

        st.divider()

        # 显示交易信号
        display_signals(signals)

        st.divider()

        # 显示指标数值
        latest = data.iloc[-1]
        cols = st.columns(4)

        with cols[0]:
            st.subheader("MACD")
            st.write(f"MACD: {latest['macd']:.3f}")
            st.write(f"Signal: {latest['macd_signal']:.3f}")
            st.write(f"Hist: {latest['macd_hist']:.3f}")

        with cols[1]:
            st.subheader("RSI(14)")
            st.write(f"RSI: {latest['rsi']:.2f}")

        with cols[2]:
            st.subheader("KDJ")
            st.write(f"K: {latest['kdj_k']:.2f}")
            st.write(f"D: {latest['kdj_d']:.2f}")
            st.write(f"J: {latest['kdj_j']:.2f}")

        with cols[3]:
            st.subheader("布林带")
            st.write(f"上轨: {latest['boll_upper']:.2f}")
            st.write(f"中轨: {latest['boll_mid']:.2f}")
            st.write(f"下轨: {latest['boll_lower']:.2f}")
            st.write(f"带宽: {latest['boll_width']*100:.2f}%")

        st.divider()

        # 绘制图表
        tab1, tab2, tab3, tab4 = st.tabs(["K线+MACD", "RSI", "KDJ", "布林带"])

        with tab1:
            fig = plot_candlestick_chart(data, f"{symbol} {stock_name} - K线图")
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            fig = plot_rsi_chart(data)
            st.plotly_chart(fig, use_container_width=True)

        with tab3:
            fig = plot_kdj_chart(data)
            st.plotly_chart(fig, use_container_width=True)

        with tab4:
            fig = plot_boll_chart(data)
            st.plotly_chart(fig, use_container_width=True)

        # 显示原始数据
        with st.expander("查看原始数据"):
            st.dataframe(data.tail(20))

@st.cache_data(ttl=180, show_spinner=False)
def get_cached_hot_stocks(market):
    """缓存热门股票数据"""
    recommender = StockRecommender()
    if market == "CN":
        return {
            'hot': recommender.get_hot_stocks_cn(limit=20),
            'gainers': recommender.get_top_gainers_cn(limit=10),
            'losers': recommender.get_top_losers_cn(limit=10)
        }
    else:
        return {'hot': recommender.get_hot_stocks_us(limit=20)}

def hot_stocks_page():
    """热门股票页面"""
    st.markdown('<h1 class="main-header">🔥 热门股票排行</h1>', unsafe_allow_html=True)

    # 使用 session state 保存热门股票页面状态
    if 'hot_market' not in st.session_state:
        st.session_state.hot_market = "CN"

    def on_hot_market_change():
        st.session_state.hot_market = st.session_state.hot_market_select

    market_index = ["CN", "US"].index(st.session_state.hot_market)
    market = st.selectbox("选择市场", options=["CN", "US"],
                         index=market_index,
                         format_func=lambda x: {"CN": "A股", "US": "美股"}[x],
                         key="hot_market_select",
                         on_change=on_hot_market_change)

    market = st.session_state.hot_market

    if st.button("刷新数据", type="primary"):
        with st.spinner("正在获取热门股票..."):
            # 清除缓存，强制重新获取
            get_cached_hot_stocks.clear()
            data = get_cached_hot_stocks(market)

            if market == "CN":
                hot = data.get('hot', [])
                gainers = data.get('gainers', [])
                losers = data.get('losers', [])

                # 调试信息
                if not hot:
                    st.warning("暂无热门股票数据，请稍后重试")
                    return

                # 热门股票
                st.subheader("📈 热门股票 TOP 20")
                df_hot = pd.DataFrame(hot)
                if not df_hot.empty:
                    df_hot = df_hot.rename(columns={
                        '代码': 'Symbol',
                        '名称': 'Name',
                        '最新价': 'Price',
                        '涨跌幅': 'Change%',
                        '换手率': 'Turnover%',
                        '成交量': 'Volume',
                        '成交额': 'Amount',
                        '热度分数': 'Score'
                    })
                    st.dataframe(df_hot, use_container_width=True)
                else:
                    st.info("暂无热门股票数据")

                # 涨幅榜
                st.subheader("📊 涨幅榜 TOP 10")
                df_gainers = pd.DataFrame(gainers)
                if not df_gainers.empty:
                    df_gainers = df_gainers.rename(columns={
                        '代码': 'Symbol',
                        '名称': 'Name',
                        '最新价': 'Price',
                        '涨跌幅': 'Change%',
                        '换手率': 'Turnover%'
                    })
                    st.dataframe(df_gainers, use_container_width=True)
                else:
                    st.info("暂无涨幅榜数据")

                # 跌幅榜
                st.subheader("📉 跌幅榜 TOP 10")
                df_losers = pd.DataFrame(losers)
                if not df_losers.empty:
                    df_losers = df_losers.rename(columns={
                        '代码': 'Symbol',
                        '名称': 'Name',
                        '最新价': 'Price',
                        '涨跌幅': 'Change%',
                        '换手率': 'Turnover%'
                    })
                    st.dataframe(df_losers, use_container_width=True)
                else:
                    st.info("暂无跌幅榜数据")

            else:
                hot = data.get('hot', [])
                df_hot = pd.DataFrame(hot)
                if not df_hot.empty:
                    st.dataframe(df_hot, use_container_width=True)
                else:
                    st.info("暂无美股热门数据")

@st.cache_data(ttl=600, show_spinner=False)
def get_cached_recommended_stocks(num_stocks):
    """缓存推荐股票数据"""
    recommender = StockRecommender()
    return recommender.get_recommended_stocks_cn(num_stocks=num_stocks)

def display_recommendation_list(recommended, strategy_name):
    """显示推荐列表"""
    if not recommended:
        st.warning(f"暂无{strategy_name}推荐股票")
        st.info("💡 可能原因：\n1. 数据获取失败（网络问题）\n2. 股票分析返回None（数据不足）\n3. 请检查日志输出")
        return

    st.success(f"{strategy_name}：为您推荐以下 {len(recommended)} 只股票")

    # 显示推荐列表
    for i, stock in enumerate(recommended, 1):
        with st.container():
            st.markdown(f"""
            <div class="stock-card">
                <h4>#{i} {stock['symbol']} {stock['name']}</h4>
                <p><strong>综合评分:</strong> {stock['score']}/100 |
                <strong>建议:</strong> {stock['rating']} |
                <strong>当前价:</strong> {stock['latest_price']:.2f}</p>
            </div>
            """, unsafe_allow_html=True)

            # 显示详细指标
            cols = st.columns(4)
            with cols[0]:
                st.write("**MACD:**", f"{stock['indicators']['macd']:.3f}")
                st.caption(stock['signals']['macd'])
            with cols[1]:
                st.write("**RSI:**", f"{stock['indicators']['rsi']}")
                st.caption(stock['signals']['rsi'])
            with cols[2]:
                st.write("**KDJ:**", f"K:{stock['indicators']['kdj_k']:.1f} D:{stock['indicators']['kdj_d']:.1f}")
                st.caption(stock['signals']['kdj'])
            with cols[3]:
                st.write("**布林带:**", f"{stock['indicators']['boll_lower']:.1f}-{stock['indicators']['boll_upper']:.1f}")
                st.caption(stock['signals']['boll'])

            st.divider()

@st.cache_data(ttl=600, show_spinner=False)
def get_cached_short_term_stocks(num_stocks):
    """获取短线推荐股票（基于短期技术指标）"""
    recommender = StockRecommender()
    return recommender.get_short_term_recommendations(num_stocks=num_stocks)

@st.cache_data(ttl=600, show_spinner=False)
def get_cached_sector_stocks(sector_name, num_stocks):
    """获取板块短线推荐股票"""
    recommender = StockRecommender()
    return recommender.get_sector_short_term_recommendations(sector_name, num_stocks=num_stocks)

def recommended_stocks_page():
    """推荐股票页面 - 短线龙头股推荐"""
    st.markdown('<h1 class="main-header">⭐ 短线龙头股推荐</h1>', unsafe_allow_html=True)

    # 使用 session state 保存推荐页面状态
    if 'rec_sector' not in st.session_state:
        st.session_state.rec_sector = "全部"
    if 'rec_num_stocks' not in st.session_state:
        st.session_state.rec_num_stocks = 5

    def on_sector_change():
        st.session_state.rec_sector = st.session_state.rec_sector_select

    def on_num_stocks_change():
        st.session_state.rec_num_stocks = st.session_state.rec_num_slider

    st.info("基于MACD、RSI、KDJ等技术指标，筛选各板块短线龙头股")

    # 板块选择
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

    # 从 session state 读取当前值
    sector = st.session_state.rec_sector
    num_stocks = st.session_state.rec_num_stocks

    # 添加清除缓存按钮
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("🔄 清除缓存", type="secondary"):
            get_cached_short_term_stocks.clear()
            get_cached_sector_stocks.clear()
            st.success("缓存已清除，请重新生成推荐")

    if st.button("生成推荐", type="primary"):
        with st.spinner(f"正在分析{sector}板块，请稍候..."):
            if sector == "全部":
                recommended = get_cached_short_term_stocks(num_stocks)
                display_recommendation_list(recommended, "短线推荐")
            else:
                recommended = get_cached_sector_stocks(sector, num_stocks)
                display_recommendation_list(recommended, f"{sector} 短线龙头股")

def display_watchlist_sidebar():
    """在侧边栏显示自选股列表"""
    watchlist = get_watchlist()

    if watchlist:
        st.markdown("### ⭐ 自选股")
        for item in watchlist:
            col1, col2 = st.columns([4, 1])
            with col1:
                # 使用更简洁的按钮样式
                display_text = f"{item['symbol']}"
                if item['name'] and item['name'] != item['symbol']:
                    display_text += f" · {item['name'][:4]}"
                if st.button(display_text, key=f"wl_{item['symbol']}_{item['market']}", use_container_width=True):
                    st.session_state.analyze_symbol = item['symbol']
                    st.session_state.analyze_market = item['market']
                    st.rerun()
            with col2:
                if st.button("✕", key=f"del_{item['symbol']}_{item['market']}", help="移除"):
                    remove_from_watchlist(item['symbol'], item['market'])
                    st.rerun()
        st.markdown("---")


def compare_stocks_page():
    """股票对比页面"""
    st.markdown('<h1 class="main-header">📊 股票对比分析</h1>', unsafe_allow_html=True)

    st.info("同时对比多只股票的关键指标，最多支持5只股票")

    # 输入股票列表
    col1, col2 = st.columns(2)

    with col1:
        symbols_input = st.text_area(
            "输入股票代码（每行一个，最多5个）",
            value="600519\n000858\n600036",
            help="输入A股股票代码，每行一个"
        )

    with col2:
        market = st.selectbox("市场", ["CN"], index=0, format_func=lambda x: "A股")

    if st.button("🔍 开始对比", type="primary"):
        symbols = [s.strip() for s in symbols_input.strip().split('\n') if s.strip()][:5]

        if len(symbols) < 2:
            st.warning("请至少输入2只股票进行对比")
            return

        with st.spinner("正在获取对比数据..."):
            comparison_data = []

            for symbol in symbols:
                try:
                    data = get_cached_stock_data(symbol, "3mo", market)
                    if data is not None and not data.empty:
                        data = TechnicalIndicators.calculate_all(data)
                        latest = data.iloc[-1]

                        # 计算涨跌幅
                        change_pct = ((latest['close'] - data.iloc[0]['close']) / data.iloc[0]['close']) * 100

                        comparison_data.append({
                            '代码': symbol,
                            '名称': fetcher.get_stock_name(symbol, market),
                            '最新价': f"{latest['close']:.2f}",
                            '涨跌幅': f"{change_pct:.2f}%",
                            '成交量': f"{latest['volume']/10000:.0f}万",
                            'RSI(14)': f"{latest['rsi']:.1f}",
                            'MACD': f"{latest['macd']:.3f}",
                            'KDJ-K': f"{latest['kdj_k']:.1f}",
                            '布林位置': '上轨附近' if latest['close'] > latest['boll_upper'] * 0.98 else '中轨附近' if latest['close'] > latest['boll_mid'] * 0.98 else '下轨附近'
                        })
                except Exception as e:
                    st.error(f"获取 {symbol} 数据失败: {str(e)}")

            if comparison_data:
                # 显示对比表格
                df = pd.DataFrame(comparison_data)
                st.subheader("📊 关键指标对比")
                st.dataframe(df, use_container_width=True)

                # 显示价格走势图对比
                st.subheader("📈 价格走势对比")
                fig = go.Figure()

                for symbol in symbols:
                    try:
                        data = get_cached_stock_data(symbol, "3mo", market)
                        if data is not None:
                            # 标准化价格（以第一天为基准100）
                            normalized_price = (data['close'] / data['close'].iloc[0]) * 100
                            fig.add_trace(go.Scatter(
                                x=data.index,
                                y=normalized_price,
                                name=f"{symbol} ({fetcher.get_stock_name(symbol, market)})",
                                mode='lines'
                            ))
                    except:
                        continue

                fig.update_layout(
                    title="标准化价格走势对比（基准=100）",
                    xaxis_title="日期",
                    yaxis_title="相对价格",
                    height=500,
                    hovermode='x unified'
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("未能获取对比数据，请检查股票代码是否正确")


def main():
    """主函数"""
    # 侧边栏导航
    with st.sidebar:
        st.title("📊 股票分析系统")
        st.markdown("---")

        # 自选股列表
        display_watchlist_sidebar()

        page = st.radio(
            "功能菜单",
            options=["个股分析", "热门股票", "智能推荐", "股票对比"],
            format_func=lambda x: {"个股分析": "📈 个股分析", "热门股票": "🔥 热门股票", "智能推荐": "⭐ 智能推荐", "股票对比": "📊 股票对比"}[x]
        )

        st.markdown("---")
        st.markdown("### 关于")
        st.markdown("""
        本系统提供：
        - 📊 K线图 + 技术指标
        - 📈 MACD、RSI、KDJ、BOLL
        - 🔥 实时热门股票排行
        - ⭐ 智能股票推荐
        - ⭐ 自选股管理

        **支持市场：**
        - A股 (中国市场)
        - 美股 (美国市场)
        - 港股 (香港市场)
        """)

        st.markdown("---")
        st.caption("⚠️ 风险提示：本系统仅供参考，不构成投资建议")

    # 页面路由
    if page == "个股分析":
        analyze_stock_page()
    elif page == "热门股票":
        hot_stocks_page()
    elif page == "智能推荐":
        recommended_stocks_page()
    elif page == "股票对比":
        compare_stocks_page()

if __name__ == "__main__":
    main()
