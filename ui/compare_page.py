"""股票对比页面 — 多股票指标对比 + 走势决策仪表盘"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from technical_indicators import TechnicalIndicators
from ui.cached_data import quote_service, resolve_cached_stock_input
from ui.loading import status_loading
from ui.analyze_page import _validate_symbol


def _u(text):
    return text.encode("ascii").decode("unicode_escape")


def _pct(value):
    if value is None or pd.isna(value):
        return "--"
    return f"{value:+.2f}%"


def _plain_pct(value):
    if value is None or pd.isna(value):
        return "--"
    return f"{value:.2f}%"


def _close_series(data):
    if data is None or data.empty or "close" not in data.columns:
        return pd.Series(dtype="float64")
    close = pd.to_numeric(data["close"], errors="coerce").dropna()
    return close[close > 0]


def _period_return(close, days):
    if close.empty:
        return None
    lookback = min(days, len(close) - 1)
    if lookback <= 0:
        return None
    start_price = close.iloc[-lookback - 1]
    latest_price = close.iloc[-1]
    if start_price <= 0:
        return None
    return (latest_price / start_price - 1) * 100


def _max_drawdown(close):
    if close.empty:
        return None
    peak = close.cummax()
    drawdown = close / peak - 1
    return drawdown.min() * 100


def _annualized_volatility(close):
    returns = close.pct_change().dropna()
    if returns.empty:
        return None
    return returns.std() * (244 ** 0.5) * 100


def _up_day_ratio(close):
    returns = close.pct_change().dropna()
    if returns.empty:
        return None
    return (returns > 0).mean() * 100


def _trend_slope(close, days=20):
    if len(close) < 3:
        return None
    window = close.tail(min(days, len(close)))
    normalized = window / window.iloc[0] * 100
    x = pd.Series(range(len(normalized)), dtype="float64")
    return float(x.cov(normalized.reset_index(drop=True)) / x.var()) if x.var() else None


def _ma_status(close):
    if close.empty:
        return "--"
    latest = close.iloc[-1]
    ma20 = close.tail(20).mean() if len(close) >= 20 else None
    ma60 = close.tail(60).mean() if len(close) >= 60 else None

    if ma20 is not None and ma60 is not None:
        if latest >= ma20 >= ma60:
            return _u(r"\u591a\u5934\u6392\u5217")
        if latest < ma20 < ma60:
            return _u(r"\u7a7a\u5934\u6392\u5217")
        if latest >= ma20:
            return _u(r"\u7ad9\u4e0aMA20")
        return _u(r"\u8dcc\u7834MA20")
    if ma20 is not None:
        return _u(r"\u7ad9\u4e0aMA20") if latest >= ma20 else _u(r"\u8dcc\u7834MA20")
    return _u(r"\u6570\u636e\u4e0d\u8db3")


def build_trend_metrics(symbol, name, data):
    """Build comparable trend/risk metrics from historical close prices."""
    close = _close_series(data)
    if close.empty:
        return None

    return {
        "symbol": symbol,
        "name": name,
        "return_20d": _period_return(close, 20),
        "return_60d": _period_return(close, 60),
        "return_120d": _period_return(close, 120),
        "return_244d": _period_return(close, 244),
        "max_drawdown": _max_drawdown(close),
        "volatility": _annualized_volatility(close),
        "up_day_ratio": _up_day_ratio(close),
        "trend_slope_20d": _trend_slope(close, 20),
        "ma_status": _ma_status(close),
        "latest_close": close.iloc[-1],
    }


def build_compare_insights(metrics):
    """Return short human-readable winners for the comparison dashboard."""
    if not metrics:
        return []

    def best_by(key, reverse=True):
        candidates = [item for item in metrics if item.get(key) is not None and not pd.isna(item.get(key))]
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: item[key], reverse=reverse)[0]

    strongest = best_by("return_20d", True)
    stable = best_by("volatility", False)
    lowest_drawdown = best_by("max_drawdown", True)
    trend = best_by("trend_slope_20d", True)

    insights = []
    if strongest:
        insights.append((_u(r"\u8fd120\u65e5\u6700\u5f3a"), strongest, _pct(strongest["return_20d"])))
    if trend:
        insights.append((_u(r"\u8d8b\u52bf\u659c\u7387\u6700\u5f3a"), trend, f"{trend['trend_slope_20d']:+.2f}"))
    if stable:
        insights.append((_u(r"\u6ce2\u52a8\u6700\u4f4e"), stable, _plain_pct(stable["volatility"])))
    if lowest_drawdown:
        insights.append((_u(r"\u56de\u64a4\u6700\u5c0f"), lowest_drawdown, _pct(lowest_drawdown["max_drawdown"])))
    return insights


def _normalized_price(close):
    return close / close.iloc[0] * 100 if not close.empty else close


def _drawdown_series(close):
    return (close / close.cummax() - 1) * 100 if not close.empty else close


def build_trend_dashboard_figure(history_by_symbol, names_by_symbol):
    """Create normalized price, drawdown and relative-strength comparison charts."""
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=(
            _u(r"\u6807\u51c6\u5316\u4ef7\u683c\uff08\u8d77\u70b9=100\uff09"),
            _u(r"\u533a\u95f4\u56de\u64a4\uff08%\uff09"),
            _u(r"\u76f8\u5bf9\u5f3a\u5f31\uff08\u76f8\u5bf9\u7b2c1\u53ea\uff0c\u767e\u5206\u70b9\uff09"),
        ),
    )

    base_normalized = None
    for symbol, data in history_by_symbol.items():
        close = _close_series(data)
        if close.empty:
            continue
        normalized = _normalized_price(close)
        label = f"{symbol} ({names_by_symbol.get(symbol, symbol)})"
        if base_normalized is None:
            base_normalized = normalized

        fig.add_trace(go.Scatter(x=close.index, y=normalized, name=label, mode="lines"), row=1, col=1)
        fig.add_trace(
            go.Scatter(x=close.index, y=_drawdown_series(close), name=f"{label} 回撤", mode="lines", showlegend=False),
            row=2,
            col=1,
        )

        relative = normalized - base_normalized.reindex(normalized.index).ffill()
        fig.add_trace(
            go.Scatter(x=close.index, y=relative, name=f"{label} 相对强弱", mode="lines", showlegend=False),
            row=3,
            col=1,
        )

    fig.update_layout(
        height=760,
        hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_family='-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif',
        margin=dict(l=20, r=20, t=50, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_yaxes(title_text=_u(r"\u76f8\u5bf9\u4ef7\u683c"), row=1, col=1)
    fig.update_yaxes(title_text=_u(r"\u56de\u64a4%"), row=2, col=1)
    fig.update_yaxes(title_text=_u(r"\u5f3a\u5f31\u5dee"), row=3, col=1)
    fig.update_xaxes(title_text=_u(r"\u65e5\u671f"), row=3, col=1)
    return fig


def _render_insight_cards(metrics):
    insights = build_compare_insights(metrics)
    if not insights:
        return

    st.subheader(_u(r"\u8d70\u52bf\u7ed3\u8bba"))
    cols = st.columns(len(insights))
    for col, (title, item, value) in zip(cols, insights):
        with col:
            st.metric(title, f"{item['name']}", value)


def _trend_metrics_dataframe(metrics):
    rows = []
    for item in metrics:
        rows.append({
            _u(r"\u4ee3\u7801"): item["symbol"],
            _u(r"\u540d\u79f0"): item["name"],
            _u(r"\u8fd120\u65e5"): _pct(item["return_20d"]),
            _u(r"\u8fd160\u65e5"): _pct(item["return_60d"]),
            _u(r"\u8fd1120\u65e5"): _pct(item["return_120d"]),
            _u(r"\u8fd11\u5e74"): _pct(item["return_244d"]),
            _u(r"\u6700\u5927\u56de\u64a4"): _pct(item["max_drawdown"]),
            _u(r"\u5e74\u5316\u6ce2\u52a8"): _plain_pct(item["volatility"]),
            _u(r"\u4e0a\u6da8\u5929\u6570\u5360\u6bd4"): _plain_pct(item["up_day_ratio"]),
            _u(r"\u8fd120\u65e5\u8d8b\u52bf\u659c\u7387"): "--" if item["trend_slope_20d"] is None else f"{item['trend_slope_20d']:+.2f}",
            _u(r"MA\u72b6\u6001"): item["ma_status"],
        })
    return pd.DataFrame(rows)


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


def _run_compare_task(raw_symbols, market):
    """后台执行股票对比数据获取和指标计算。"""
    resolved_stocks, warnings = resolve_compare_inputs(raw_symbols, market, limit=5)
    symbols = [item["symbol"] for item in resolved_stocks]
    names_by_symbol = {item["symbol"]: item["name"] for item in resolved_stocks}
    recognized = [
        f"{item['query']} → {item['name']} ({item['symbol']})"
        if item["query"] != item["name"] and item["query"] != item["symbol"]
        else f"{item['name']} ({item['symbol']})"
        for item in resolved_stocks
    ]

    if len(symbols) < 2:
        return {
            "warnings": warnings,
            "error": "请至少输入2只有效股票进行对比",
            "recognized": recognized,
        }

    stocks_to_fetch = [{'code': s, 'name': names_by_symbol.get(s, s)} for s in symbols]
    results = quote_service.fetch_multiple_stocks(
        stocks_to_fetch, period='1y', market=market, max_workers=5
    )

    comparison_data = []
    trend_metrics = []
    history_by_symbol = {}
    errors = []
    for symbol in symbols:
        result = results.get(symbol)
        if result and result['success']:
            try:
                data = TechnicalIndicators.calculate_all(result['data'])
                history_by_symbol[symbol] = result['data']
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
                metrics = build_trend_metrics(
                    symbol,
                    names_by_symbol.get(symbol) or quote_service.get_stock_name(symbol, market),
                    result['data'],
                )
                if metrics:
                    trend_metrics.append(metrics)
            except Exception as exc:
                errors.append(f"处理 {symbol} 数据失败: {exc}")
        else:
            errors.append(f"获取 {symbol} 数据失败")

    return {
        "warnings": warnings,
        "recognized": recognized,
        "comparison_data": comparison_data,
        "trend_metrics": trend_metrics,
        "history_by_symbol": history_by_symbol,
        "names_by_symbol": names_by_symbol,
        "errors": errors,
    }


def _render_compare_result(result):
    for warning in result.get("warnings", []):
        st.warning(warning)
    recognized = result.get("recognized") or []
    if recognized:
        st.caption(_u(r"\u5df2\u8bc6\u522b\uff1a") + _u(r"\uff0c").join(recognized))
    if result.get("error"):
        st.warning(result["error"])
        return
    for error in result.get("errors", []):
        st.warning(error)

    comparison_data = result.get("comparison_data") or []
    trend_metrics = result.get("trend_metrics") or []
    history_by_symbol = result.get("history_by_symbol") or {}
    names_by_symbol = result.get("names_by_symbol") or {}

    if comparison_data:
        df = pd.DataFrame(comparison_data)
        st.subheader("关键指标对比")
        st.dataframe(df, use_container_width=True)

        st.subheader("价格走势对比")
        if trend_metrics:
            _render_insight_cards(trend_metrics)
            st.markdown(
                _u(r"\u4e0b\u8868\u628a\u300c\u6da8\u5f97\u591a\u300d\u300c\u56de\u64a4\u5c0f\u300d\u300c\u6ce2\u52a8\u4f4e\u300d\u300c\u8d8b\u52bf\u5f3a\u300d\u62c6\u5f00\u770b\uff0c\u907f\u514d\u53ea\u770b\u4e00\u6761\u4ef7\u683c\u7ebf\u5c31\u4e0b\u7ed3\u8bba\u3002")
            )
            st.dataframe(_trend_metrics_dataframe(trend_metrics), use_container_width=True)
            fig = build_trend_dashboard_figure(history_by_symbol, names_by_symbol)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning(_u(r"\u6682\u65e0\u8db3\u591f\u5386\u53f2\u6570\u636e\u751f\u6210\u8d70\u52bf\u5bf9\u6bd4\u4eea\u8868\u76d8"))
    else:
        st.warning("未能获取对比数据，请检查股票代码是否正确")


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
        with status_loading(f"\u6b63\u5728\u5e76\u53d1\u83b7\u53d6 {len(raw_symbols)} \u53ea\u80a1\u7968\u6570\u636e...", 20):
            st.session_state.compare_result = _run_compare_task(raw_symbols, market)

    if st.session_state.get("compare_result"):
        _render_compare_result(st.session_state.compare_result)
