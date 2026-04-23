"""
股票分析系统 - Web版本
使用Streamlit构建
"""
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 导入原有模块
from data_fetcher import StockDataFetcher
from technical_indicators import TechnicalIndicators
from stock_recommendation import StockRecommender

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
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.subheader("MACD")
        if "金叉" in signals['macd']:
            st.markdown(f"<span class='buy-signal'>📈 {signals['macd']}</span>", unsafe_allow_html=True)
        elif "死叉" in signals['macd']:
            st.markdown(f"<span class='sell-signal'>📉 {signals['macd']}</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span class='neutral-signal'>➖ {signals['macd']}</span>", unsafe_allow_html=True)

    with col2:
        st.subheader("RSI")
        if "超卖" in signals['rsi']:
            st.markdown(f"<span class='buy-signal'>🔵 {signals['rsi']}</span>", unsafe_allow_html=True)
        elif "超买" in signals['rsi']:
            st.markdown(f"<span class='sell-signal'>🔴 {signals['rsi']}</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span class='neutral-signal'>⚪ {signals['rsi']}</span>", unsafe_allow_html=True)

    with col3:
        st.subheader("KDJ")
        if "买入" in signals['kdj'] or "超卖" in signals['kdj']:
            st.markdown(f"<span class='buy-signal'>📈 {signals['kdj']}</span>", unsafe_allow_html=True)
        elif "卖出" in signals['kdj'] or "超买" in signals['kdj']:
            st.markdown(f"<span class='sell-signal'>📉 {signals['kdj']}</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span class='neutral-signal'>➖ {signals['kdj']}</span>", unsafe_allow_html=True)

    with col4:
        st.subheader("布林带")
        if "反弹" in signals['boll'] or "偏多" in signals['boll']:
            st.markdown(f"<span class='buy-signal'>📈 {signals['boll']}</span>", unsafe_allow_html=True)
        elif "回调" in signals['boll'] or "偏空" in signals['boll']:
            st.markdown(f"<span class='sell-signal'>📉 {signals['boll']}</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span class='neutral-signal'>➖ {signals['boll']}</span>", unsafe_allow_html=True)

    # 综合建议
    st.divider()
    recommendation = signals['recommendation']
    if "买入" in recommendation:
        st.success(f"### 💡 综合建议: {recommendation}")
    elif "卖出" in recommendation:
        st.error(f"### 💡 综合建议: {recommendation}")
    else:
        st.info(f"### 💡 综合建议: {recommendation}")

def analyze_stock_page():
    """个股分析页面"""
    st.markdown('<h1 class="main-header">📊 股票技术分析</h1>', unsafe_allow_html=True)

    # 输入区域
    col1, col2, col3 = st.columns(3)

    with col1:
        symbol = st.text_input("股票代码", value="000001", help="A股如: 000001, 600519 | 美股如: AAPL, TSLA")

    with col2:
        market = st.selectbox("市场", options=["CN", "US", "HK"], index=0,
                             format_func=lambda x: {"CN": "A股", "US": "美股", "HK": "港股"}[x])

    with col3:
        period = st.selectbox("时间周期", options=["1mo", "3mo", "6mo", "1y", "2y"], index=3)

    if st.button("🔍 开始分析", type="primary", use_container_width=True):
        with st.spinner("正在获取数据并计算指标..."):
            fetcher = StockDataFetcher()

            # 获取基本信息
            info = fetcher.get_stock_info(symbol, market)

            # 获取实时行情
            quote = fetcher.get_realtime_quote(symbol, market)

            # 获取历史数据
            data = fetcher.get_stock_data(symbol, period=period, market=market)

            if data is None or data.empty:
                st.error(f"未能获取到 {symbol} 的数据，请检查代码是否正确")
                return

            # 计算指标
            data = TechnicalIndicators.calculate_all(data)
            signals = TechnicalIndicators.get_signals(data)

            # 显示基本信息
            st.divider()

            # 股票标题
            stock_name = ""
            if market == "CN" and info:
                stock_name = info.get('股票简称', symbol)
            elif info:
                stock_name = info.get('shortName', symbol)

            st.header(f"{symbol} {stock_name}")

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

def hot_stocks_page():
    """热门股票页面"""
    st.markdown('<h1 class="main-header">🔥 热门股票排行</h1>', unsafe_allow_html=True)

    market = st.selectbox("选择市场", options=["CN", "US"], index=0,
                         format_func=lambda x: {"CN": "A股", "US": "美股"}[x])

    if st.button("刷新数据", type="primary"):
        with st.spinner("正在获取热门股票..."):
            recommender = StockRecommender()

            if market == "CN":
                # 热门股票
                hot = recommender.get_hot_stocks_cn(limit=20)
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

                # 涨幅榜
                st.subheader("📊 涨幅榜 TOP 10")
                gainers = recommender.get_top_gainers_cn(limit=10)
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

                # 跌幅榜
                st.subheader("📉 跌幅榜 TOP 10")
                losers = recommender.get_top_losers_cn(limit=10)
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
                hot = recommender.get_hot_stocks_us(limit=20)
                df_hot = pd.DataFrame(hot)
                if not df_hot.empty:
                    st.dataframe(df_hot, use_container_width=True)

def recommended_stocks_page():
    """推荐股票页面"""
    st.markdown('<h1 class="main-header">⭐ 智能推荐股票</h1>', unsafe_allow_html=True)

    st.info("基于MACD、RSI、KDJ、布林带等多因子技术分析，自动筛选优质股票")

    num_stocks = st.slider("推荐数量", min_value=5, max_value=20, value=10)

    if st.button("生成推荐", type="primary"):
        with st.spinner("正在分析股票池，请稍候..."):
            recommender = StockRecommender()
            recommended = recommender.get_recommended_stocks_cn(num_stocks=num_stocks)

            if not recommended:
                st.warning("暂无推荐股票，请稍后重试")
                return

            st.success(f"根据技术分析，为您推荐以下 {len(recommended)} 只股票")

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

def main():
    """主函数"""
    # 侧边栏导航
    with st.sidebar:
        st.title("📊 股票分析系统")
        st.markdown("---")

        page = st.radio(
            "功能菜单",
            options=["个股分析", "热门股票", "智能推荐"],
            format_func=lambda x: {"个股分析": "📈 个股分析", "热门股票": "🔥 热门股票", "智能推荐": "⭐ 智能推荐"}[x]
        )

        st.markdown("---")
        st.markdown("### 关于")
        st.markdown("""
        本系统提供：
        - 📊 K线图 + 技术指标
        - 📈 MACD、RSI、KDJ、BOLL
        - 🔥 实时热门股票排行
        - ⭐ 智能股票推荐

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

if __name__ == "__main__":
    main()
