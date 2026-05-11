"""股票对比页面 — 多股票指标对比 + 标准化走势"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from technical_indicators import TechnicalIndicators
from data_fetcher import StockDataFetcher
from ui.cached_data import fetcher
from ui.analyze_page import _validate_symbol


def compare_stocks_page():
    """股票对比页面"""
    st.markdown('<h1 class="main-header">股票对比</h1>', unsafe_allow_html=True)

    st.info("同时对比多只股票的关键指标，最多支持5只股票（并发获取，速度更快）")

    col1, col2 = st.columns(2)

    with col1:
        symbols_input = st.text_area(
            "输入股票代码（每行一个，最多5个）",
            value="600519\n000858\n600036",
            help="输入A股股票代码，每行一个"
        )

    with col2:
        market = st.selectbox("市场", ["CN"], index=0, format_func=lambda x: "A股")

    if st.button("开始对比", type="primary"):
        raw_symbols = [s.strip() for s in symbols_input.strip().split('\n') if s.strip()][:5]

        symbols = []
        for s in raw_symbols:
            ok, err = _validate_symbol(s, market)
            if ok:
                symbols.append(s)
            else:
                st.warning(f"跳过无效代码「{s}」：{err}")

        if len(symbols) < 2:
            st.warning("请至少输入2只有效股票进行对比")
            return

        with st.spinner(f"正在并发获取 {len(symbols)} 只股票数据..."):
            progress_bar = st.progress(0)
            status_text = st.empty()

            stocks_to_fetch = [{'code': s, 'name': s} for s in symbols]

            status_text.text("并发获取股票数据...")
            results = StockDataFetcher.fetch_multiple_stocks(
                stocks_to_fetch, period='1y', market=market, max_workers=5
            )

            progress_bar.progress(60)
            status_text.text("计算技术指标...")

            comparison_data = []
            for symbol in symbols:
                result = results.get(symbol)
                if result and result['success']:
                    try:
                        data = TechnicalIndicators.calculate_all(result['data'])
                        latest = data.iloc[-1]

                        quote = fetcher.get_realtime_quote(symbol, market)
                        if quote and quote.get('price'):
                            price = quote['price']
                            change_pct = quote.get('change', 0)
                        else:
                            price = latest['close']
                            change_pct = ((latest['close'] - data.iloc[0]['close']) / data.iloc[0]['close']) * 100

                        comparison_data.append({
                            '代码': symbol,
                            '名称': fetcher.get_stock_name(symbol, market),
                            '最新价': f"{price:.2f}",
                            '涨跌幅': f"{change_pct:+.2f}%",
                            '成交量': (
                                f"{latest['volume']/1e8:.1f}亿" if latest['volume'] >= 1e8 else
                                f"{latest['volume']/1e4:.0f}万" if latest['volume'] >= 1e4 else
                                f"{latest['volume']:.0f}"
                            ),
                            'RSI(6)': f"{latest['rsi_6']:.2f}",
                            'MACD': f"{latest['macd']:.2f}",
                            'KDJ-K': f"{latest['kdj_k']:.2f}",
                            '布林位置': '上轨附近' if latest['close'] > latest['boll_upper'] * 0.98 else '中轨附近' if latest['close'] > latest['boll_mid'] * 0.98 else '下轨附近'
                        })
                    except Exception as e:
                        st.error(f"处理 {symbol} 数据失败: {str(e)}")
                else:
                    st.warning(f"获取 {symbol} 数据失败")

            progress_bar.progress(100)
            progress_bar.empty()
            status_text.empty()

            if comparison_data:
                df = pd.DataFrame(comparison_data)
                st.subheader("关键指标对比")
                st.dataframe(df, use_container_width=True)

                st.subheader("价格走势对比")
                fig = go.Figure()

                for symbol in symbols:
                    result = results.get(symbol)
                    if result and result['success']:
                        try:
                            data = result['data']
                            normalized_price = (data['close'] / data['close'].iloc[0]) * 100
                            fig.add_trace(go.Scatter(
                                x=data.index,
                                y=normalized_price,
                                name=f"{symbol} ({fetcher.get_stock_name(symbol, market)})",
                                mode='lines'
                            ))
                        except Exception:
                            continue

                fig.update_layout(
                    title="标准化价格走势对比（基准=100）",
                    xaxis_title="日期",
                    yaxis_title="相对价格",
                    height=500,
                    hovermode='x unified',
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font_family='-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif',
                    margin=dict(l=20, r=20, t=40, b=20)
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("未能获取对比数据，请检查股票代码是否正确")
