"""图表函数 — Plotly K线/RSI/KDJ/MACD/BOLL/分时图"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from config import RSI_OVERBOUGHT, RSI_OVERSOLD, KDJ_OVERBOUGHT, KDJ_OVERSOLD
from chart_utils import resolve_color_scheme, MA_CONFIG


def _indicator_layout(title, height=280, **extra):
    """共享指标图 layout 配置，避免 RSI/KDJ/BOLL 三处重复"""
    layout = dict(
        title=dict(text=title or ""),
        height=height,
        hovermode='x unified',
        hoverlabel=dict(bgcolor='rgba(0,0,0,0.7)', font=dict(size=11, color='#fff')),
        showlegend=True,
        legend=dict(font=dict(size=10), orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_family='-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif',
        margin=dict(l=20, r=20, t=40, b=20),
    )
    layout.update(extra)
    return layout


def _latest_number(data, column, precision=2):
    """安全读取最后一条实时指标值。"""
    if column not in data.columns or data.empty:
        return "--"
    value = data[column].iloc[-1]
    if pd.isna(value):
        return "--"
    return f"{float(value):.{precision}f}"


def latest_indicator_values(data, indicator):
    """返回图表外展示用的最新指标值。"""
    mapping = {
        "macd": [("DIF", "macd"), ("DEA", "macd_signal"), ("柱", "macd_hist")],
        "rsi": [("RSI6", "rsi_6"), ("RSI12", "rsi_12"), ("RSI24", "rsi_24")],
        "kdj": [("K", "kdj_k"), ("D", "kdj_d"), ("J", "kdj_j")],
        "boll": [("价格", "close"), ("上轨", "boll_upper"), ("中轨", "boll_mid"), ("下轨", "boll_lower")],
        "main_accumulation": [("主力吸货", "main_accumulation"), ("风险", "accumulation_risk"), ("涨跌", "accumulation_trend")],
    }
    return [(label, _latest_number(data, column)) for label, column in mapping.get(indicator, [])]


def latest_ma_values(data):
    """返回日K图表右上角展示用的最新均线值。"""
    return [(f"MA{period}", _latest_number(data, f"ma{period}")) for period in (5, 10, 20, 30)]


def _category_axis_ticks(x_values, max_ticks=7):
    values = list(x_values)
    if len(values) <= max_ticks:
        return values
    step = max(1, len(values) // (max_ticks - 1))
    ticks = values[::step]
    if ticks[-1] != values[-1]:
        ticks.append(values[-1])
    return ticks


def plot_candlestick_chart(data, title=""):
    """使用 Plotly 绘制独立 K 线 + 均线图。"""

    scheme_name = st.session_state.get('color_scheme')
    market = st.session_state.get('analyze_market', 'CN')
    colors = resolve_color_scheme(scheme_name, market)
    inc_color = colors['increasing']
    dec_color = colors['decreasing']

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=data.index,
        open=data['open'], high=data['high'], low=data['low'], close=data['close'],
        name="K线",
        increasing_line_color=inc_color,
        decreasing_line_color=dec_color,
        showlegend=False,
    ))

    for ma_conf in MA_CONFIG.values():
        col = f'ma{ma_conf["period"]}'
        if col in data.columns:
            fig.add_trace(go.Scatter(
                x=data.index, y=data[col],
                mode='lines',
                name=f'MA{ma_conf["period"]}',
                line=dict(color=ma_conf['color'], width=1),
            ))

    x_values = data.index.strftime("%Y-%m-%d") if hasattr(data.index, "strftime") else data.index
    tick_values = _category_axis_ticks(x_values)
    fig.update_traces(x=x_values)
    fig.update_layout(
        title=dict(text=title or ""),
        height=360,
        hovermode='x unified',
        hoverlabel=dict(bgcolor='rgba(0,0,0,0.7)', font=dict(size=11, color='#fff')),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_family='-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif',
        margin=dict(l=20, r=20, t=24, b=20),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(
        type="category",
        tickmode="array",
        tickvals=tick_values,
        showticklabels=False,
        rangeslider_visible=False,
        showgrid=False,
        zeroline=False,
    )
    fig.update_yaxes(showgrid=False, zeroline=False)
    return fig


def _volume_series_in_hands(data):
    volume = data['volume']
    unit = str(getattr(data, "attrs", {}).get("volume_unit") or "").lower()
    if unit in {"share", "shares", "股"}:
        return volume / 100
    return volume


def _quote_volume_in_hands(quote):
    if not quote or quote.get("volume") is None:
        return None
    volume = float(quote["volume"])
    unit = str(quote.get("volume_unit") or "hand").lower()
    if unit in {"share", "shares", "股"}:
        return volume / 100
    return volume


def _quote_date(quote):
    value = (quote or {}).get("quote_date") or (quote or {}).get("date")
    if not value:
        return None
    date_value = pd.to_datetime(value, errors="coerce")
    if pd.isna(date_value):
        return None
    return date_value.normalize()


def plot_volume_chart(data, quote=None):
    """绘制独立成交量图，按同花顺风格展示量、MA5、MA10。"""
    scheme_name = st.session_state.get('color_scheme')
    market = st.session_state.get('analyze_market', 'CN')
    colors = resolve_color_scheme(scheme_name, market)
    inc_color = colors['increasing']
    dec_color = colors['decreasing']

    fig = go.Figure()
    if 'volume' not in data.columns:
        return fig

    volume = _volume_series_in_hands(data).astype(float).copy()
    x_values = data.index.strftime("%Y-%m-%d") if hasattr(data.index, "strftime") else data.index
    close_values = data['close'].copy()
    open_values = data['open'].copy()
    quote_volume = _quote_volume_in_hands(quote)
    if quote_volume is not None and not volume.empty:
        quote_day = _quote_date(quote)
        if quote_day is None:
            quote_volume = None
        last_day = data.index[-1].normalize() if isinstance(data.index, pd.DatetimeIndex) else None
        if quote_volume is not None and quote_day is not None and last_day is not None and quote_day > last_day:
            volume = pd.concat([volume, pd.Series([quote_volume], index=[quote_day])])
            close_values = pd.concat([close_values, pd.Series([quote.get("price", close_values.iloc[-1])], index=[quote_day])])
            open_values = pd.concat([open_values, pd.Series([quote.get("open", open_values.iloc[-1])], index=[quote_day])])
            x_values = volume.index.strftime("%Y-%m-%d")
        elif quote_volume is not None:
            volume.iloc[-1] = quote_volume

    tick_values = _category_axis_ticks(x_values)
    vol_colors = [inc_color if close_values.iloc[i] >= open_values.iloc[i] else dec_color
                  for i in range(len(volume))]
    volume_wan = volume / 10000
    volume_ma5_wan = volume.rolling(5).mean() / 10000
    volume_ma10_wan = volume.rolling(10).mean() / 10000
    fig.add_trace(go.Bar(
        x=x_values,
        y=volume_wan,
        name="量",
        marker_color=vol_colors,
        hovertemplate='量: %{y:.2f}万手<extra></extra>',
    ))
    fig.add_trace(go.Scatter(
        x=x_values,
        y=volume_ma5_wan,
        mode='lines',
        name='MA5',
        line=dict(color='#8e8e93', width=1.2),
        hovertemplate='MA5: %{y:.2f}万手<extra></extra>',
    ))
    fig.add_trace(go.Scatter(
        x=x_values,
        y=volume_ma10_wan,
        mode='lines',
        name='MA10',
        line=dict(color='#a855f7', width=1.2),
        hovertemplate='MA10: %{y:.2f}万手<extra></extra>',
    ))
    fig.update_layout(**_indicator_layout(
        "",
        height=260,
        margin=dict(l=20, r=20, t=24, b=20),
    ))
    fig.update_xaxes(type="category", tickmode="array", tickvals=tick_values, showticklabels=False, showgrid=False, zeroline=False)
    fig.update_yaxes(title_text="万手", showgrid=False, zeroline=False)
    return fig


def plot_macd_chart(data):
    """绘制独立 MACD 图表。"""
    scheme_name = st.session_state.get('color_scheme')
    market = st.session_state.get('analyze_market', 'CN')
    colors = resolve_color_scheme(scheme_name, market)
    inc_color = colors['increasing']
    dec_color = colors['decreasing']

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=data.index, y=data['macd'],
        mode='lines', name='DIF (快线)',
        line=dict(color='#42a5f5', width=1.4),
    ))
    fig.add_trace(go.Scatter(
        x=data.index, y=data['macd_signal'],
        mode='lines', name='DEA (慢线)',
        line=dict(color='#ff7043', width=1.4),
    ))
    macd_hist_colors = [inc_color if value >= 0 else dec_color for value in data['macd_hist'].fillna(0)]
    fig.add_trace(go.Bar(
        x=data.index, y=data['macd_hist'],
        name='MACD柱',
        marker_color=macd_hist_colors,
    ))
    x_values = data.index.strftime("%Y-%m-%d") if hasattr(data.index, "strftime") else data.index
    tick_values = _category_axis_ticks(x_values)
    fig.update_traces(x=x_values)
    fig.add_hline(y=0, line_dash="solid", line_color="gray", opacity=0.5)
    fig.update_layout(**_indicator_layout("", height=300, margin=dict(l=20, r=20, t=24, b=20)))
    fig.update_xaxes(type="category", tickmode="array", tickvals=tick_values, showticklabels=False, showgrid=False, zeroline=False)
    fig.update_yaxes(showgrid=False, zeroline=False)
    return fig


def plot_rsi_chart(data):
    """绘制RSI图表"""
    scheme_name = st.session_state.get('color_scheme')
    market = st.session_state.get('analyze_market', 'CN')
    colors = resolve_color_scheme(scheme_name, market)
    inc_color = colors['increasing']
    dec_color = colors['decreasing']

    fig = go.Figure()

    fig.add_trace(go.Scatter(x=data.index, y=data['rsi_6'], name='RSI(6)', line=dict(color='red', width=2)))
    fig.add_trace(go.Scatter(x=data.index, y=data['rsi_12'], name='RSI(12)', line=dict(color='orange', width=2)))
    fig.add_trace(go.Scatter(x=data.index, y=data['rsi_24'], name='RSI(24)', line=dict(color='purple', width=2)))
    fig.add_hline(y=RSI_OVERBOUGHT, line_dash="dash", line_color=dec_color, annotation_text=f"超买({RSI_OVERBOUGHT})")
    fig.add_hline(y=RSI_OVERSOLD, line_dash="dash", line_color=inc_color, annotation_text=f"超卖({RSI_OVERSOLD})")

    fig.add_hrect(y0=0, y1=RSI_OVERSOLD, line_width=0, fillcolor=inc_color, opacity=0.08, name="超卖区")
    fig.add_hrect(y0=RSI_OVERBOUGHT, y1=100, line_width=0, fillcolor=dec_color, opacity=0.08, name="超买区")

    x_values = data.index.strftime("%Y-%m-%d") if hasattr(data.index, "strftime") else data.index
    tick_values = _category_axis_ticks(x_values)
    fig.update_traces(x=x_values)
    fig.update_layout(**_indicator_layout("", height=280, yaxis_range=[0, 100], margin=dict(l=20, r=20, t=24, b=20)))

    fig.update_xaxes(type="category", tickmode="array", tickvals=tick_values, showticklabels=False, showgrid=False, zeroline=False)
    fig.update_yaxes(showgrid=False, zeroline=False)

    return fig


def plot_kdj_chart(data):
    """绘制KDJ图表"""
    scheme_name = st.session_state.get('color_scheme')
    market = st.session_state.get('analyze_market', 'CN')
    colors = resolve_color_scheme(scheme_name, market)
    inc_color = colors['increasing']
    dec_color = colors['decreasing']

    fig = go.Figure()

    fig.add_trace(go.Scatter(x=data.index, y=data['kdj_k'], name='K', line=dict(color='blue')))
    fig.add_trace(go.Scatter(x=data.index, y=data['kdj_d'], name='D', line=dict(color='orange')))
    fig.add_trace(go.Scatter(x=data.index, y=data['kdj_j'], name='J', line=dict(color='purple')))
    fig.add_hline(y=KDJ_OVERBOUGHT, line_dash="dash", line_color=dec_color, annotation_text=f"超买({KDJ_OVERBOUGHT})")
    fig.add_hline(y=KDJ_OVERSOLD, line_dash="dash", line_color=inc_color, annotation_text=f"超卖({KDJ_OVERSOLD})")

    # KDJ金叉/死叉标记
    k_vals = data['kdj_k'].values
    d_vals = data['kdj_d'].values
    kdj_golden = np.where((k_vals > d_vals) & (np.roll(k_vals <= d_vals, 1)))[0]
    kdj_death = np.where((k_vals < d_vals) & (np.roll(k_vals >= d_vals, 1)))[0]
    kdj_golden = kdj_golden[kdj_golden > 0]
    kdj_death = kdj_death[kdj_death > 0]
    if len(kdj_golden) > 0:
        fig.add_trace(go.Scatter(
            x=data.index[kdj_golden].strftime("%Y-%m-%d") if hasattr(data.index, "strftime") else data.index[kdj_golden],
            y=data['kdj_k'].iloc[kdj_golden],
            mode='markers', name='KDJ金叉', marker=dict(symbol='triangle-up', size=12, color=inc_color, line=dict(width=1)),
            showlegend=True, hovertemplate='KDJ金叉<br>%{x}<br>K: %{y:.1f}'))
    if len(kdj_death) > 0:
        fig.add_trace(go.Scatter(
            x=data.index[kdj_death].strftime("%Y-%m-%d") if hasattr(data.index, "strftime") else data.index[kdj_death],
            y=data['kdj_k'].iloc[kdj_death],
            mode='markers', name='KDJ死叉', marker=dict(symbol='triangle-down', size=12, color=dec_color, line=dict(width=1)),
            showlegend=True, hovertemplate='KDJ死叉<br>%{x}<br>K: %{y:.1f}'))

    fig.add_hrect(y0=0, y1=KDJ_OVERSOLD, line_width=0, fillcolor=inc_color, opacity=0.08, name="超卖区")
    fig.add_hrect(y0=KDJ_OVERBOUGHT, y1=100, line_width=0, fillcolor=dec_color, opacity=0.08, name="超买区")

    x_values = data.index.strftime("%Y-%m-%d") if hasattr(data.index, "strftime") else data.index
    tick_values = _category_axis_ticks(x_values)
    fig.update_traces(x=x_values, selector=lambda trace: trace.mode != 'markers')
    fig.update_layout(**_indicator_layout("", margin=dict(l=20, r=20, t=24, b=20)))
    fig.update_xaxes(type="category", tickmode="array", tickvals=tick_values, showticklabels=False, showgrid=False, zeroline=False)
    fig.update_yaxes(showgrid=False, zeroline=False)

    return fig


def plot_boll_chart(data):
    """绘制布林带图表"""
    fig = go.Figure()

    x_values = data.index.strftime("%Y-%m-%d") if hasattr(data.index, "strftime") else data.index
    tick_values = _category_axis_ticks(x_values)
    fig.add_trace(go.Scatter(x=x_values, y=data['close'], name='价格', line=dict(color='#f8fafc', width=2.4)))
    fig.add_trace(go.Scatter(x=x_values, y=data['boll_upper'], name='上轨', line=dict(color='red')))
    fig.add_trace(go.Scatter(x=x_values, y=data['boll_mid'], name='中轨', line=dict(color='blue')))
    fig.add_trace(go.Scatter(x=x_values, y=data['boll_lower'], name='下轨', line=dict(color='green')))

    # 填充布林带区域
    fig.add_trace(go.Scatter(
        x=list(x_values) + list(x_values)[::-1],
        y=data['boll_upper'].tolist() + data['boll_lower'].tolist()[::-1],
        fill='toself',
        fillcolor='rgba(0,100,80,0.1)',
        line=dict(color='rgba(255,255,255,0)'),
        name='布林带区间'
    ))

    fig.update_layout(**_indicator_layout(
        "",
        height=300,
        margin=dict(l=20, r=20, t=24, b=20),
        legend=dict(font=dict(size=10), orientation='h', yanchor='top', y=1.02, xanchor='left', x=0.06),
    ))
    fig.update_xaxes(type="category", tickmode="array", tickvals=tick_values, showticklabels=False, showgrid=False, zeroline=False)
    fig.update_yaxes(showgrid=False, zeroline=False)

    return fig


def plot_main_accumulation_chart(data):
    """绘制同花顺公式「主力吸货」指标图。"""
    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=data.index,
        y=data['main_accumulation'],
        name='主力吸货',
        marker_color='rgba(255, 51, 255, 0.72)',
        hovertemplate='主力吸货 %{y:.2f}<extra></extra>',
    ))
    fig.add_trace(go.Scatter(
        x=data.index,
        y=data['accumulation_risk'],
        mode='lines',
        name='风险',
        line=dict(color='#34c759', width=1.8),
        hovertemplate='风险 %{y:.2f}<extra></extra>',
    ))
    fig.add_trace(go.Scatter(
        x=data.index,
        y=data['accumulation_trend'],
        mode='lines',
        name='涨跌',
        line=dict(color='#ff3b30', width=1.8),
        hovertemplate='涨跌 %{y:.2f}<extra></extra>',
    ))
    fig.add_hline(y=0, line_dash="solid", line_color="#8e8e93", opacity=0.5)
    fig.update_layout(**_indicator_layout(
        "",
        height=300,
        margin=dict(l=20, r=20, t=28, b=20),
        legend=dict(font=dict(size=10), orientation='h', yanchor='bottom', y=1.04, xanchor='left', x=0),
    ))
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(showgrid=False, zeroline=False)
    return fig


def plot_intraday_chart(df, quote):
    """分时图 — 同花顺式价格/均价 + 成交量分区展示。"""
    if df is None or df.empty:
        return None

    df = df.copy()
    df['time'] = pd.to_datetime(df['time'], errors='coerce')
    df = df.dropna(subset=['time']).sort_values('time')
    if df.empty:
        return None

    for col in ['close', 'avg_price', 'volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    prev = None
    if quote:
        prev = quote.get('prev_close')
        try:
            prev = float(prev) if prev is not None else None
        except (TypeError, ValueError):
            prev = None

    price_median = df['close'].dropna().median() if 'close' in df.columns else None
    if prev and pd.notna(price_median) and price_median > 0:
        if prev > price_median * 1.3 or prev < price_median * 0.7:
            prev = None

    interval = df.attrs.get('interval') or ''
    latest_time = df['time'].iloc[-1].strftime('%H:%M')

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.74, 0.26],
        vertical_spacing=0.03,
        specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
    )

    fig.add_trace(go.Scatter(
        x=df['time'], y=df['close'],
        mode='lines', name='价格',
        line=dict(color='#0071e3', width=1.35, shape='spline', smoothing=0.65),
        hovertemplate='价格 %{y:.2f}<extra></extra>'
    ), row=1, col=1, secondary_y=False)

    if 'avg_price' in df.columns and df['avg_price'].notna().any():
        fig.add_trace(go.Scatter(
            x=df['time'], y=df['avg_price'],
            mode='lines', name='均价',
            line=dict(color='#f9ab00', width=1.15, shape='spline', smoothing=0.75),
            hovertemplate='均价 %{y:.2f}<extra></extra>'
        ), row=1, col=1, secondary_y=False)

    if prev:
        fig.add_hline(y=prev, line=dict(color='#8e8e93', width=0.8, dash='dot'),
                      annotation_text=f'昨收 {prev:.2f}', row=1, col=1)

    volume = df['volume'] if 'volume' in df.columns else pd.Series([0] * len(df))
    volume_colors = np.where(df['close'].diff().fillna(0) >= 0, 'rgba(255,59,48,0.45)', 'rgba(52,199,89,0.45)')
    fig.add_trace(go.Bar(
        x=df['time'], y=volume,
        name='量',
        marker=dict(color=volume_colors),
        hovertemplate='量 %{y:.0f}手<extra></extra>'
    ), row=2, col=1)

    change_pct = quote.get('change', 0) if quote else 0
    title_color = '#ff3b30' if change_pct > 0 else '#34c759' if change_pct < 0 else '#8e8e93'

    data_date = df['time'].iloc[0].date()
    tick_times = ['09:30','10:00','10:30','11:00','11:30',
                  '13:00','13:30','14:00','14:30','15:00']
    tickvals = [pd.Timestamp.combine(data_date, pd.Timestamp(t).time()) for t in tick_times]

    price_values = pd.concat([df['close'], df.get('avg_price', pd.Series(dtype=float))]).dropna()
    y_range = None
    if prev and not price_values.empty:
        max_delta = max(abs(price_values.max() - prev), abs(price_values.min() - prev), prev * 0.005)
        y_range = [prev - max_delta * 1.12, prev + max_delta * 1.12]
        fig.update_yaxes(
            range=[(y_range[0] / prev - 1) * 100, (y_range[1] / prev - 1) * 100],
            ticksuffix='%',
            tickformat='.2f',
            showgrid=False,
            zeroline=False,
            secondary_y=True,
            row=1,
            col=1,
        )
    elif not price_values.empty:
        low = float(price_values.min())
        high = float(price_values.max())
        pad = max((high - low) * 0.18, max(abs(high), 1) * 0.003)
        y_range = [low - pad, high + pad]

    fig.update_layout(
        title=dict(text=f"分时走势 · {interval or '1分钟'} · {latest_time}", font=dict(size=14, color=title_color)),
        hovermode='x unified',
        height=360,
        bargap=0,
        showlegend=False,
        margin=dict(l=20, r=34, t=54, b=22),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_family='-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif',
    )
    fig.update_xaxes(
        title='',
        tickvals=tickvals,
        tickformat='%H:%M',
        showgrid=False,
        zeroline=False,
        row=2,
        col=1,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, showticklabels=False, row=1, col=1)
    fig.update_yaxes(
        title='价格',
        range=y_range,
        side='left',
        showgrid=True,
        gridcolor='rgba(128,128,128,0.12)',
        zeroline=False,
        row=1,
        col=1,
        secondary_y=False,
    )
    fig.update_yaxes(
        title='涨跌幅',
        showgrid=False,
        zeroline=False,
        row=1,
        col=1,
        secondary_y=True,
    )
    fig.update_yaxes(
        title='量(手)',
        showgrid=True,
        gridcolor='rgba(128,128,128,0.08)',
        zeroline=False,
        row=2,
        col=1,
    )

    return fig
