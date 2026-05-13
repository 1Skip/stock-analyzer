"""股票对比页面 — 多股票指标对比 + 标准化走势"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from technical_indicators import TechnicalIndicators
from ui.cached_data import quote_service, resolve_cached_stock_input
from ui.loading import status_loading
from ui.analyze_page import _validate_symbol


def _u(text):
    return text.encode("ascii").decode("unicode_escape")


def resolve_compare_inputs(raw_inputs, market, limit=5):
    """Resolve compare inputs into stock codes and display names."""
    resolved = []
    warnings = []
    seen = set()

    for raw_input in raw_inputs[:limit]:
        query = str(raw_input or "").strip()
        if not query:
            continue

        ok, err = _validate_symbol(query, market)
        if ok:
            symbol = query.upper() if market != "CN" else query
            name = quote_service.get_stock_name(symbol, market)
        else:
            match = resolve_cached_stock_input(query, market)
            if not match:
                reason = err or _u(r'\u672a\u627e\u5230\u5339\u914d\u80a1\u7968')
                warnings.append(
                    f"{_u(r'\u8df3\u8fc7\u65e0\u6cd5\u8bc6\u522b\u7684\u8f93\u5165\u300c')}{query}"
                    f"{_u(r'\u300d\uff1a')}{reason}"
                    f"{_u(r'\uff1b\u8bf7\u68c0\u67e5\u7b80\u79f0\u662f\u5426\u6709\u9519\u5b57\u6216\u987a\u5e8f\u98a0\u5012\uff0c\u4e5f\u53ef\u76f4\u63a5\u8f93\u51656\u4f4d\u4ee3\u7801\u3002')}"
                )
                continue
            symbol, name = match

        if symbol in seen:
            warnings.append(f"{_u(r'\u8df3\u8fc7\u91cd\u590d\u80a1\u7968\u300c')}{query}{_u(r'\u300d\uff1a\u5df2\u52a0\u5165')} {symbol}")
            continue

        seen.add(symbol)
        resolved.append({"symbol": symbol, "name": name or symbol, "query": query})

    return resolved, warnings


def compare_stocks_page():
    """股票对比页面"""
    st.markdown('<h1 class="main-header">股票对比</h1>', unsafe_allow_html=True)

    st.info("同时对比多只股票的关键指标，最多支持5只股票（并发获取，速度更快）")

    col1, col2 = st.columns(2)

    with col1:
        symbols_input = st.text_area(
            _u(r"\u80a1\u7968\u4ee3\u7801\u6216\u540d\u79f0\uff08\u6bcf\u884c\u4e00\u4e2a\uff0c\u6700\u591a5\u4e2a\uff09"),
            value=_u(r"\u8d35\u5dde\u8305\u53f0\n\u4e94\u7cae\u6db2\n\u62db\u5546\u94f6\u884c"),
            help=_u(r"\u652f\u6301\u8f93\u5165\u80a1\u7968\u540d\u79f0\u3001\u7b80\u79f0\u6216\u4ee3\u7801\uff0c\u4f8b\u5982\uff1a\u8305\u53f0\u3001600519\u3001\u62db\u5546\u94f6\u884c")
        )

    with col2:
        market = st.selectbox("市场", ["CN"], index=0, format_func=lambda x: "A股")

    if st.button("开始对比", type="primary"):
        raw_symbols = [s.strip() for s in symbols_input.strip().split('\n') if s.strip()]
        resolved_stocks, warnings = resolve_compare_inputs(raw_symbols, market, limit=5)

        for warning in warnings:
            st.warning(warning)

        symbols = [item["symbol"] for item in resolved_stocks]
        names_by_symbol = {item["symbol"]: item["name"] for item in resolved_stocks}

        if resolved_stocks:
            st.caption(
                _u(r"\u5df2\u8bc6\u522b\uff1a") + _u(r"\uff0c").join(
                    f"{item['query']} → {item['name']} ({item['symbol']})"
                    if item["query"] != item["name"] and item["query"] != item["symbol"]
                    else f"{item['name']} ({item['symbol']})"
                    for item in resolved_stocks
                )
            )

        if len(symbols) < 2:
            st.warning("请至少输入2只有效股票进行对比")
            return

        with status_loading(f"\u6b63\u5728\u5e76\u53d1\u83b7\u53d6 {len(symbols)} \u53ea\u80a1\u7968\u6570\u636e...", 20):
            progress_bar = st.progress(0)
            status_text = st.empty()

            stocks_to_fetch = [{'code': s, 'name': names_by_symbol.get(s, s)} for s in symbols]

            status_text.text("并发获取股票数据...")
            results = quote_service.fetch_multiple_stocks(
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

                        quote = quote_service.get_realtime_quote(symbol, market)
                        if quote and quote.get('price'):
                            price = quote['price']
                            change_pct = quote.get('change', 0)
                        else:
                            price = latest['close']
                            change_pct = ((latest['close'] - data.iloc[0]['close']) / data.iloc[0]['close']) * 100

                        comparison_data.append({
                            '代码': symbol,
                            _u(r'\u540d\u79f0'): names_by_symbol.get(symbol) or quote_service.get_stock_name(symbol, market),
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
                                name=f"{symbol} ({names_by_symbol.get(symbol) or quote_service.get_stock_name(symbol, market)})",
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
