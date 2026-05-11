"""图表函数 — Plotly K线/RSI/KDJ/BOLL/分时图"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from config import RSI_OVERBOUGHT, RSI_OVERSOLD, KDJ_OVERBOUGHT, KDJ_OVERSOLD
from chart_utils import resolve_color_scheme, MA_CONFIG


def _indicator_layout(title, height=280, **extra):
    """共享指标图 layout 配置，避免 RSI/KDJ/BOLL 三处重复"""
    layout = dict(
        title=title,
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


def plot_candlestick_chart(data, title=""):
    """使用 Plotly 绘制 K 线 + 成交量 + MACD 三合一图"""

    scheme_name = st.session_state.get('color_scheme')
    market = st.session_state.get('analyze_market', 'CN')
    colors = resolve_color_scheme(scheme_name, market)
    inc_color = colors['increasing']
    dec_color = colors['decreasing']

    from plotly.subplots import make_subplots

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.55, 0.15, 0.30],
        subplot_titles=("K线 + 均线", "成交量", ""),
    )

    # --- Row 1: K线 + 均线 ---
    fig.add_trace(go.Candlestick(
        x=data.index,
        open=data['open'], high=data['high'], low=data['low'], close=data['close'],
        name="K线",
        increasing_line_color=inc_color,
        decreasing_line_color=dec_color,
        showlegend=False,
    ), row=1, col=1)

    for ma_conf in MA_CONFIG.values():
        col = f'ma{ma_conf["period"]}'
        if col in data.columns:
            fig.add_trace(go.Scatter(
                x=data.index, y=data[col],
                mode='lines',
                name=f'MA{ma_conf["period"]}',
                line=dict(color=ma_conf['color'], width=1),
            ), row=1, col=1)

    # --- Row 2: 成交量 ---
    if 'volume' in data.columns:
        vol_colors = [inc_color if data['close'].iloc[i] >= data['open'].iloc[i] else dec_color
                      for i in range(len(data))]
        fig.add_trace(go.Bar(
            x=data.index, y=data['volume'],
            name="成交量",
            marker_color=vol_colors,
            showlegend=False,
        ), row=2, col=1)

    # --- Row 3: MACD ---
    if 'macd' in data.columns and 'macd_signal' in data.columns and 'macd_hist' in data.columns:
        fig.add_trace(go.Scatter(
            x=data.index, y=data['macd'],
            mode='lines', name='DIF (快线)',
            line=dict(color='#42a5f5', width=1),
        ), row=3, col=1)
        fig.add_trace(go.Scatter(
            x=data.index, y=data['macd_signal'],
            mode='lines', name='DEA (慢线)',
            line=dict(color='#ff7043', width=1),
        ), row=3, col=1)
        macd_hist_colors = [inc_color if v >= 0 else dec_color
                           for v in data['macd_hist'].fillna(0)]
        fig.add_trace(go.Bar(
            x=data.index, y=data['macd_hist'],
            name='MACD柱',
            marker_color=macd_hist_colors,
            showlegend=True,
        ), row=3, col=1)

        # MACD 零轴参考线 + 标识
        fig.add_hline(y=0, line_dash="solid", line_color="gray", opacity=0.5, row=3, col=1)
        fig.add_annotation(
            xref="x3 domain", yref="y3 domain", x=0.01, y=0.95,
            text="<b>MACD</b>",
            showarrow=False,
            font=dict(size=12, color="gray"),
            bgcolor="rgba(0,0,0,0)",
        )

    # 布局
    fig.update_layout(
        height=650,
        hovermode='x unified',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_family='-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif',
        margin=dict(l=20, r=20, t=40, b=20),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(showgrid=False, zeroline=False)

    # 子图标题更显眼
    for annotation in fig.layout.annotations:
        annotation.font.size = 13
        annotation.font.color = '#8e8e93'

    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': True})


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

    fig.update_layout(**_indicator_layout("RSI", height=280, yaxis_range=[0, 100]))

    fig.update_xaxes(showgrid=False, zeroline=False)
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
            x=data.index[kdj_golden], y=data['kdj_k'].iloc[kdj_golden],
            mode='markers', name='KDJ金叉', marker=dict(symbol='triangle-up', size=12, color=inc_color, line=dict(width=1)),
            showlegend=True, hovertemplate='KDJ金叉<br>%{x}<br>K: %{y:.1f}'))
    if len(kdj_death) > 0:
        fig.add_trace(go.Scatter(
            x=data.index[kdj_death], y=data['kdj_k'].iloc[kdj_death],
            mode='markers', name='KDJ死叉', marker=dict(symbol='triangle-down', size=12, color=dec_color, line=dict(width=1)),
            showlegend=True, hovertemplate='KDJ死叉<br>%{x}<br>K: %{y:.1f}'))

    fig.add_hrect(y0=0, y1=KDJ_OVERSOLD, line_width=0, fillcolor=inc_color, opacity=0.08, name="超卖区")
    fig.add_hrect(y0=KDJ_OVERBOUGHT, y1=100, line_width=0, fillcolor=dec_color, opacity=0.08, name="超买区")

    fig.update_layout(**_indicator_layout("KDJ"))
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(showgrid=False, zeroline=False)

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

    fig.update_layout(**_indicator_layout("BOLL", height=300))
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(showgrid=False, zeroline=False)

    return fig


def plot_intraday_chart(df, quote):
    """分时图 — 当日5分钟价格走势 + 均价线（数据来自新浪财经）"""
    if df is None or df.empty:
        return None

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df['time'], y=df['close'],
        mode='lines', name='价格',
        line=dict(color='#0071e3', width=1.5),
        hovertemplate='%{y:.2f}<extra></extra>'
    ))

    if 'avg_price' in df.columns and df['avg_price'].notna().any():
        fig.add_trace(go.Scatter(
            x=df['time'], y=df['avg_price'],
            mode='lines', name='均价',
            line=dict(color='#f9ab00', width=1, dash='dash'),
            hovertemplate='均价 %{y:.2f}<extra></extra>'
        ))

    if quote and quote.get('prev_close'):
        prev = quote['prev_close']
        fig.add_hline(y=prev, line=dict(color='#8e8e93', width=0.8, dash='dot'),
                      annotation_text=f'昨收 {prev:.2f}')

    fig.add_trace(go.Bar(
        x=df['time'], y=df['volume'],
        name='量', yaxis='y2',
        marker=dict(color='rgba(26,115,232,0.15)'),
        hovertemplate='量 %{y:.0f}<extra></extra>'
    ))

    change_pct = quote.get('change', 0) if quote else 0
    title_color = '#ff3b30' if change_pct > 0 else '#34c759' if change_pct < 0 else '#8e8e93'

    data_date = df['time'].iloc[0].date()
    tick_times = ['09:30','10:00','10:30','11:00','11:30',
                  '13:00','13:30','14:00','14:30','15:00']
    tickvals = [pd.Timestamp.combine(data_date, pd.Timestamp(t).time()) for t in tick_times]

    fig.update_layout(
        title=dict(text=f"分时走势", font=dict(size=14, color=title_color)),
        xaxis=dict(title='', tickvals=tickvals, tickformat='%H:%M',
                    showgrid=False, zeroline=False),
        yaxis=dict(title='价格', side='left', showgrid=True, gridcolor='rgba(128,128,128,0.1)'),
        yaxis2=dict(title='', overlaying='y', side='right', showticklabels=False,
                     showgrid=False),
        hovermode='x unified',
        height=280,
        bargap=0,
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
        margin=dict(l=20, r=20, t=40, b=20),
        font_family='-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif',
    )

    return fig
