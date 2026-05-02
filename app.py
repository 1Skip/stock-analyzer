"""
股票分析系统 - Web版本 (优化版)
使用Streamlit构建，带缓存加速
"""
import re
import streamlit as st
import pandas as pd
import numpy as np
import html
import plotly.graph_objects as go

# 导入原有模块
from data_fetcher import StockDataFetcher
from technical_indicators import TechnicalIndicators
from stock_recommendation import StockRecommender
from watchlist import add_to_watchlist, remove_from_watchlist, get_watchlist, is_in_watchlist, get_watchlist_summary
from config import (
    CACHE_TTL_REALTIME, CACHE_TTL_STOCK_DATA, CACHE_TTL_STOCK_INFO,
    CACHE_TTL_HOT_STOCKS,
    RSI_OVERBOUGHT, RSI_OVERSOLD, KDJ_OVERBOUGHT, KDJ_OVERSOLD,
    DEFAULT_COLOR_SCHEME, COLOR_SCHEMES,
    AI_ENABLED, AI_MODEL, AI_API_KEY, AI_BASE_URL, AI_TEMPERATURE,
    MARKET_INDEX_ENABLED, INDEX_WATCHLIST,
)
from ai_analysis import build_indicator_snapshot, call_ai_analysis, run_multi_agent_analysis
from chart_utils import resolve_color_scheme, MA_CONFIG
from streamlit_lightweight_charts import renderLightweightCharts

# 初始化缓存数据获取器
fetcher = StockDataFetcher()

@st.cache_data(ttl=CACHE_TTL_STOCK_DATA, max_entries=64, show_spinner=False)
def get_cached_stock_data(symbol, period, market):
    """缓存股票数据获取"""
    try:
        return fetcher.get_stock_data(symbol, period=period, market=market)
    except Exception as e:
        return None

@st.cache_data(ttl=CACHE_TTL_STOCK_INFO, max_entries=128, show_spinner=False)
def get_cached_stock_info(symbol, market):
    """缓存股票基本信息"""
    try:
        return fetcher.get_stock_info(symbol, market)
    except Exception as e:
        return {}

@st.cache_data(ttl=CACHE_TTL_REALTIME, max_entries=64, show_spinner=False)
def get_cached_realtime_quote(symbol, market):
    """缓存实时行情 - 10秒缓存确保实时性"""
    try:
        return fetcher.get_realtime_quote(symbol, market)
    except Exception as e:
        return None


@st.cache_data(ttl=60, show_spinner=False)
def get_cached_intraday_data(symbol, market):
    """缓存分时数据 - 60秒缓存，仅A股"""
    try:
        return fetcher.get_intraday_data(symbol, market)
    except Exception:
        return None

# 页面配置
st.set_page_config(
    page_title="股票分析系统",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义CSS样式 — Apple × Tesla 设计体系
# 8px间距梯度 / 四级字体层级 / 完整色板 / 亮暗双主题兼容
st.markdown("""
<style>
    /* ===== 设计变量 ===== */
    :root {
        --space-4: 4px;
        --space-8: 8px;
        --space-12: 12px;
        --space-16: 16px;
        --space-24: 24px;
        --space-32: 32px;
        --space-48: 48px;
        --font-title: 1.5rem;
        --font-section: 1.1rem;
        --font-body: 0.9rem;
        --font-caption: 0.75rem;
        --color-primary: #1a73e8;
        --color-rise: #e53935;
        --color-fall: #2e7d32;
        --color-warning: #f9a825;
        --color-flat: #757575;
    }

    /* ===== 全局字体 ===== */
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
        font-size: var(--font-body);
        font-weight: 400;
    }

    /* ===== 等宽数字 ===== */
    [data-testid="stMetricValue"], [data-testid="stDataFrame"] td {
        font-feature-settings: "tnum";
        font-variant-numeric: tabular-nums;
    }

    /* ===== 页面标题 ===== */
    .main-header {
        font-size: var(--font-title);
        font-weight: 600;
        letter-spacing: -0.02em;
        color: inherit;
        margin-bottom: var(--space-24);
    }

    /* ===== 信号徽章 ===== */
    .signal-badge {
        display: inline-block;
        padding: var(--space-4) var(--space-12);
        border-radius: 20px;
        font-size: var(--font-caption);
        font-weight: 500;
        margin: 0 2px;
    }
    .signal-badge.buy  { background: rgba(229,57,53,0.08); color: var(--color-rise); }
    .signal-badge.sell { background: rgba(46,125,50,0.08); color: var(--color-fall); }
    .signal-badge.neutral { background: rgba(128,128,128,0.06); color: inherit; opacity: 0.5; }

    /* ===== 卡片 ===== */
    .stock-card {
        background: rgba(128, 128, 128, 0.04);
        border-radius: 14px;
        padding: 1.25rem;
        margin: 0.6rem 0;
        transition: background 0.2s ease;
    }
    .stock-card:hover {
        background: rgba(128, 128, 128, 0.08);
    }

    /* ===== 自选股条目 ===== */
    .watchlist-item {
        background: rgba(128, 128, 128, 0.04);
        border-radius: var(--space-8);
        padding: var(--space-8);
        margin: var(--space-4) 0;
        transition: background 0.2s ease;
    }
    .watchlist-item:hover {
        background: rgba(128, 128, 128, 0.08);
    }

    /* ===== 按钮 ===== */
    .stButton button {
        border-radius: var(--space-12) !important;
        font-weight: 500;
        border: none;
        transition: all 0.15s ease;
    }
    .stButton button:active {
        transform: scale(0.97);
    }
    .stButton button[data-kind="primary"] {
        background-color: #333;
        color: #fff;
    }
    .stButton button[data-kind="secondary"] {
        background-color: rgba(128, 128, 128, 0.1);
        color: inherit;
    }

    /* ===== 侧边栏 ===== */
    [data-testid="stSidebar"] {
        background-color: rgba(128, 128, 128, 0.02);
    }
    [data-testid="stSidebar"] .stRadio label {
        padding: 0.4rem 0.75rem;
        border-radius: 10px;
        transition: background 0.2s ease;
    }
    [data-testid="stSidebar"] hr {
        margin: 0.8rem 0;
        opacity: 0.2;
    }

    /* ===== Metric 指标卡片 ===== */
    [data-testid="stMetric"] {
        background: rgba(128, 128, 128, 0.04);
        border-radius: var(--space-12);
        padding: 0.75rem;
        transition: background 0.2s ease;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.75rem !important;
        font-weight: 600 !important;
    }
    [data-testid="stMetricDelta"] {
        font-size: 1rem !important;
        font-weight: 500 !important;
    }

    /* ===== Tab ===== */
    .stTabs [role="tab"] {
        font-weight: 500;
        border-radius: 10px;
        transition: background 0.2s ease;
    }

    /* ===== DataFrame ===== */
    [data-testid="stDataFrame"] {
        border-radius: var(--space-12);
        overflow: hidden;
    }
    [data-testid="stDataFrame"] table {
        border-radius: var(--space-12);
    }
    [data-testid="stDataFrame"] th {
        font-weight: 500;
        font-size: var(--font-caption);
        text-transform: uppercase;
        letter-spacing: 0.05em;
        opacity: 0.6;
    }

    /* ===== Expander ===== */
    [data-testid="stExpander"] {
        border-radius: var(--space-12);
        border: none !important;
    }

    /* ===== SelectBox / TextInput ===== */
    [data-testid="stTextInput"] input,
    [data-testid="stSelectbox"] div[role="combobox"],
    .stSelectbox [data-baseweb="select"] {
        border-radius: 10px !important;
    }

    /* ===== Divider ===== */
    hr {
        opacity: 0.2;
        margin: var(--space-24) 0;
    }

    /* ===== 图表区块小标题 ===== */
    .chart-section-title {
        font-size: var(--font-caption);
        font-weight: 500;
        opacity: 0.45;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin: 20px 0 6px 0;
    }
</style>
""", unsafe_allow_html=True)

def plot_candlestick_chart(data, title=""):
    """使用 TradingView lightweight-charts 绘制 K 线 + 成交量 + MACD"""

    scheme_name = st.session_state.get('color_scheme')
    market = st.session_state.get('analyze_market', 'CN')
    colors = resolve_color_scheme(scheme_name, market)
    inc_color = colors['increasing']
    dec_color = colors['decreasing']

    def to_time(idx):
        if hasattr(idx, 'strftime'):
            return idx.strftime('%Y-%m-%d')
        return str(idx)[:10]

    chart_bg = "rgba(0,0,0,0)"
    is_light = st.get_option("theme.base") == "light"
    text_color = "#131722" if is_light else "#d1d4dc"
    grid_color = "rgba(0, 0, 0, 0.1)" if is_light else "rgba(66, 66, 66, 0.3)"
    border_color = "rgba(0, 0, 0, 0.15)" if is_light else "rgba(66, 66, 66, 0.4)"
    uid = hash(tuple(data.index)) & 0x7fffffff

    # --- 图1: K线 + 均线 ---
    candles = []
    for idx, row in data.iterrows():
        candles.append({
            "time": to_time(idx),
            "open": float(row['open']),
            "high": float(row['high']),
            "low": float(row['low']),
            "close": float(row['close']),
        })

    series1 = [{
        "type": "Candlestick",
        "data": candles,
        "options": {
            "upColor": inc_color,
            "downColor": dec_color,
            "borderVisible": False,
            "wickUpColor": inc_color,
            "wickDownColor": dec_color
        }
    }]

    for ma_conf in MA_CONFIG.values():
        col = f'ma{ma_conf["period"]}'
        if col in data.columns:
            ma_data = []
            for idx, row in data.iterrows():
                if pd.notna(row[col]):
                    ma_data.append({"time": to_time(idx), "value": float(row[col])})
            series1.append({
                "type": "Line",
                "data": ma_data,
                "options": {"color": ma_conf['color'], "lineWidth": 1}
            })

    st.markdown("<b>K线 + 均线</b>", unsafe_allow_html=True)
    renderLightweightCharts([{
        "chart": {
            "height": 400,
            "layout": {"background": {"type": "solid", "color": chart_bg}, "textColor": text_color},
            "grid": {"vertLines": {"color": grid_color}, "horzLines": {"color": grid_color}},
            "crosshair": {"mode": 0},
            "rightPriceScale": {"scaleMargins": {"top": 0.05, "bottom": 0.05}, "borderColor": border_color},
            "timeScale": {"borderColor": border_color},
        },
        "series": series1,
    }], f"lwc1_{uid}")

    # --- 图2: 成交量 ---
    vol_data = []
    if 'volume' in data.columns:
        for idx, row in data.iterrows():
            if pd.notna(row['volume']):
                vol_data.append({
                    "time": to_time(idx),
                    "value": float(row['volume']),
                    "color": inc_color if row['close'] >= row['open'] else dec_color
                })

    st.markdown("<b>成交量</b>", unsafe_allow_html=True)
    renderLightweightCharts([{
        "chart": {
            "height": 100,
            "layout": {"background": {"type": "solid", "color": chart_bg}, "textColor": text_color},
            "grid": {"vertLines": {"color": grid_color}, "horzLines": {"color": grid_color}},
            "timeScale": {"visible": False},
            "rightPriceScale": {"borderColor": border_color},
        },
        "series": [{
            "type": "Histogram",
            "data": vol_data,
            "options": {"priceFormat": {"type": "volume"}},
            "priceScale": {"scaleMargins": {"top": 0, "bottom": 0}},
        }],
    }], f"lwc2_{uid}")

    # --- 图3: MACD ---
    macd_line, macd_signal, macd_hist = [], [], []
    if 'macd' in data.columns:
        for idx, row in data.iterrows():
            t = to_time(idx)
            if pd.notna(row.get('macd')):
                macd_line.append({"time": t, "value": float(row['macd'])})
            if pd.notna(row.get('macd_signal')):
                macd_signal.append({"time": t, "value": float(row['macd_signal'])})
            if pd.notna(row.get('macd_hist')):
                h = float(row['macd_hist'])
                macd_hist.append({"time": t, "value": h, "color": inc_color if h >= 0 else dec_color})

    st.markdown("<b>MACD</b>", unsafe_allow_html=True)
    renderLightweightCharts([{
        "chart": {
            "height": 150,
            "layout": {"background": {"type": "solid", "color": chart_bg}, "textColor": text_color},
            "grid": {"vertLines": {"color": grid_color}, "horzLines": {"color": grid_color}},
            "timeScale": {"borderColor": border_color},
            "rightPriceScale": {"borderColor": border_color},
        },
        "series": [
            {"type": "Line", "data": macd_line, "options": {"color": "#42a5f5", "lineWidth": 1}},
            {"type": "Line", "data": macd_signal, "options": {"color": "#ff7043", "lineWidth": 1}},
            {"type": "Histogram", "data": macd_hist, "options": {}},
        ],
    }], f"lwc3_{uid}")

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


def plot_rsi_chart(data):
    """绘制RSI图表"""
    scheme_name = st.session_state.get('color_scheme')
    market = st.session_state.get('analyze_market', 'CN')
    colors = resolve_color_scheme(scheme_name, market)
    inc_color = colors['increasing']
    dec_color = colors['decreasing']

    fig = go.Figure()

    # 显示6日、12日、24日RSI
    fig.add_trace(go.Scatter(x=data.index, y=data['rsi_6'], name='RSI(6)', line=dict(color='red', width=2)))
    fig.add_trace(go.Scatter(x=data.index, y=data['rsi_12'], name='RSI(12)', line=dict(color='orange', width=2)))
    fig.add_trace(go.Scatter(x=data.index, y=data['rsi_24'], name='RSI(24)', line=dict(color='purple', width=2)))
    fig.add_hline(y=RSI_OVERBOUGHT, line_dash="dash", line_color=dec_color, annotation_text=f"超买({RSI_OVERBOUGHT})")
    fig.add_hline(y=RSI_OVERSOLD, line_dash="dash", line_color=inc_color, annotation_text=f"超卖({RSI_OVERSOLD})")

    # 超买超卖色带
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

    # 超买超卖色带
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

    # 价格折线
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df['time'], y=df['close'],
        mode='lines', name='价格',
        line=dict(color='#1a73e8', width=1.5),
        hovertemplate='%{y:.2f}<extra></extra>'
    ))

    # 均价线
    if 'avg_price' in df.columns and df['avg_price'].notna().any():
        fig.add_trace(go.Scatter(
            x=df['time'], y=df['avg_price'],
            mode='lines', name='均价',
            line=dict(color='#f9ab00', width=1, dash='dash'),
            hovertemplate='均价 %{y:.2f}<extra></extra>'
        ))

    # 昨收线
    if quote and quote.get('prev_close'):
        prev = quote['prev_close']
        fig.add_hline(y=prev, line=dict(color='#808080', width=0.8, dash='dot'),
                      annotation_text=f'昨收 {prev:.2f}')

    # 成交量柱状图（叠加在底部）
    fig.add_trace(go.Bar(
        x=df['time'], y=df['volume'],
        name='量', yaxis='y2',
        marker=dict(color='rgba(26,115,232,0.15)'),
        hovertemplate='量 %{y:.0f}<extra></extra>'
    ))

    # 双Y轴布局
    change_pct = quote.get('change', 0) if quote else 0
    title_color = '#e53935' if change_pct > 0 else '#2e7d32' if change_pct < 0 else '#808080'

    # 30分钟间隔刻度（A股交易时段）
    today = pd.Timestamp.now().date()
    tick_times = ['09:30','10:00','10:30','11:00','11:30',
                  '13:00','13:30','14:00','14:30','15:00']
    tickvals = [pd.Timestamp.combine(today, pd.Timestamp(t).time()) for t in tick_times]
    x_range = [tickvals[0], tickvals[-1]]  # 固定X轴范围覆盖完整交易时段

    fig.update_layout(
        title=dict(text=f"分时走势", font=dict(size=14, color=title_color)),
        xaxis=dict(title='', tickvals=tickvals, range=x_range, tickformat='%H:%M',
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


def display_signals(signals):
    """显示交易信号 — 4个徽章横排 + 综合建议"""
    if 'error' in signals:
        st.warning(f"{signals['error']}")
        return

    def _signal_class(label):
        if "金叉" in label or "超卖" in label or "反弹" in label or "偏多" in label:
            return "buy"
        if "死叉" in label or "超买" in label or "回调" in label or "偏空" in label:
            return "sell"
        return "neutral"

    badges_html = ""
    for key, label in [("MACD", "macd"), ("RSI", "rsi"), ("KDJ", "kdj"), ("布林带", "boll")]:
        text = signals.get(label, '--')
        cls = _signal_class(text)
        badges_html += f'<span class="signal-badge {cls}" style="font-size:1rem">{key} · {html.escape(text)}</span>'

    st.markdown(f'<div style="margin:12px 0;font-size:1.05rem">{badges_html}</div>', unsafe_allow_html=True)

    recommendation = signals.get('recommendation', '')
    if recommendation:
        st.markdown(f'<p style="font-size:1.35rem;font-weight:700;margin-top:8px">综合: {html.escape(recommendation)}</p>', unsafe_allow_html=True)

AI_MODEL_OPTIONS = {
    # 国内模型
    "deepseek/deepseek-chat": "DeepSeek V3",
    "deepseek/deepseek-reasoner": "DeepSeek R1",
    "deepseek/deepseek-v4-pro": "DeepSeek V4 Pro",
    "zhipuai/glm-4-flash": "智谱 GLM-4 Flash（免费）",
    "zhipuai/glm-4": "智谱 GLM-4",
    "moonshot/moonshot-v1-8k": "Kimi (Moonshot)",
    "moonshot/moonshot-v1-32k": "Kimi 32K (Moonshot)",
    "dashscope/qwen-plus": "通义千问 Qwen-Plus",
    "dashscope/qwen-max": "通义千问 Qwen-Max",
    "baichuan/baichuan2-turbo": "百川 Baichuan2-Turbo",
    "baichuan/baichuan3-turbo": "百川 Baichuan3-Turbo",
    # 国际模型
    "gemini/gemini-2.5-flash": "Gemini 2.5 Flash（免费）",
    "gemini/gemini-2.5-pro": "Gemini 2.5 Pro",
    "openai/gpt-4o": "GPT-4o",
    "claude-sonnet-4-6": "Claude Sonnet 4.6",
    "claude-opus-4-7": "Claude Opus 4.7",
}


def _detect_provider(api_key):
    """根据 API Key 前缀自动检测厂商"""
    if not api_key:
        return None
    key = api_key.strip()
    if key.startswith("AIza"):
        return ("gemini", "gemini/gemini-2.5-flash")
    if key.startswith("sk-ant"):
        return ("claude", "claude-sonnet-4-6")
    if "." in key and len(key) > 30 and not key.startswith("sk-"):
        # 智谱 API Key 格式：{id}.{secret}
        return ("zhipuai", "zhipuai/glm-4-flash")
    return None


def _show_setup_form(symbol="", period=""):
    """显示 API Key 和模型配置表单"""
    st.markdown("#### 设置 API Key")
    api_key = st.text_input("API Key", type="password", key="ai_setup_key",
                            placeholder="输入你的 API Key")

    # 自动检测厂商
    detected = _detect_provider(api_key)
    if detected:
        provider_name, default_model_key = detected
        if st.session_state.get("ai_model") != default_model_key:
            st.session_state.ai_model = default_model_key
            st.session_state.ai_setup_model = default_model_key
            st.toast(f"检测到 {provider_name.upper()} API Key，已自动匹配模型")

    default_model = st.session_state.get("ai_model") or AI_MODEL
    model_keys = list(AI_MODEL_OPTIONS.keys())
    default_index = model_keys.index(default_model) if default_model in model_keys else 0

    # 用 form 包裹，防止 selectbox 变化触发 rerun 导致分析数据丢失
    with st.form(key="ai_setup_form"):
        model = st.selectbox("模型", options=model_keys,
                             format_func=lambda x: AI_MODEL_OPTIONS[x],
                             index=default_index,
                             key="ai_setup_model")
        if st.form_submit_button("保存配置", type="primary"):
            if not api_key.strip():
                st.error("API Key 不能为空")
            else:
                st.session_state.ai_api_key = api_key.strip()
                st.session_state.ai_model = model
                if symbol:
                    st.session_state[f"ai_change_cfg_{symbol}_{period}"] = False
                st.rerun()
    st.caption("获取 API Key: [Google AI Studio](https://aistudio.google.com/app/apikey)")


def _show_analysis_ui(data, signals, symbol, stock_name, period, api_key, model):
    """显示 AI 分析按钮和结果"""
    cache_key = f"ai_result_{symbol}_{period}"
    multi_cache_key = f"ai_multi_result_{symbol}_{period}"

    if cache_key not in st.session_state:
        st.session_state[cache_key] = None
    if multi_cache_key not in st.session_state:
        st.session_state[multi_cache_key] = None

    use_multi = st.checkbox("多Agent协作模式（技术+风险+决策三Agent协作）",
                            key=f"ai_multi_{symbol}_{period}")

    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        if st.button("AI 分析", type="primary", key=f"ai_btn_{symbol}_{period}"):
            error_msg = None
            try:
                snapshot = build_indicator_snapshot(data, signals, symbol, stock_name)
                if use_multi:
                    with st.spinner("多Agent协作分析中（技术分析+风险评估+综合决策）..."):
                        result = run_multi_agent_analysis(
                            snapshot, model, api_key, AI_BASE_URL
                        )
                    st.session_state[multi_cache_key] = result
                    st.session_state[cache_key] = None
                else:
                    with st.spinner("AI 正在分析技术指标..."):
                        result = call_ai_analysis(
                            snapshot, model, api_key, AI_BASE_URL, AI_TEMPERATURE
                        )
                    st.session_state[cache_key] = result
                    st.session_state[multi_cache_key] = None
            except Exception as e:
                st.session_state[cache_key] = None
                st.session_state[multi_cache_key] = None
                error_msg = str(e)
            if error_msg:
                st.error(f"分析失败：{error_msg}")
    with col_info:
        model_label = AI_MODEL_OPTIONS.get(model, model)
        st.caption(f"当前模型: {model_label}")

    # 单Agent 结果渲染
    result = st.session_state[cache_key]
    if result:
        def _clean(text):
            if not isinstance(text, str):
                return text
            return re.sub(r'^#{1,3}\s*', '', text, flags=re.MULTILINE)

        st.markdown("#### 核心结论")
        st.markdown(_clean(result.get("核心结论", "无")))

        risks = result.get("风险提示", [])
        if risks:
            st.markdown("#### 风险提示")
            for r in risks:
                st.markdown(f"- {_clean(r)}")

        levels = result.get("关键点位", {})
        if levels:
            st.markdown("#### 关键点位")
            cols = st.columns(len(levels))
            for i, (name, value) in enumerate(levels.items()):
                with cols[i]:
                    st.metric(name, value)

        suggestion = result.get("操作参考", "")
        if suggestion:
            st.markdown("#### 操作参考")
            st.markdown(_clean(suggestion))

        st.caption(f"模型: {model_label} | 以上为 AI 自动分析，不构成投资建议")

    # 多Agent 结果渲染
    multi_result = st.session_state[multi_cache_key]
    if multi_result:
        tech = multi_result.get("technical", {})
        risk = multi_result.get("risk", {})
        decision = multi_result.get("decision", {})

        # 决策综合 — 核心结论
        dec_struct = decision.get("structured", {})
        if dec_struct:
            conclusion = dec_struct.get("核心结论", "")
            score = dec_struct.get("技术面评分", "")
            confidence = dec_struct.get("信心度", "")
            if conclusion:
                st.markdown("#### 核心结论")
                score_badge = {"偏多": "🟢", "偏空": "🔴", "中性": "🟡"}.get(score, "")
                conf_badge = {"高": "高", "中": "中", "低": "低"}.get(confidence, confidence)
                st.markdown(f"{score_badge} {conclusion}（信心度: {conf_badge}）")

        # 技术分析
        tech_struct = tech.get("structured", {})
        if tech_struct:
            with st.expander("技术指标解读", expanded=False):
                for key, label in [("MACD解读", "MACD"), ("RSI解读", "RSI"),
                                   ("KDJ解读", "KDJ"), ("布林带解读", "布林带"),
                                   ("均线解读", "均线"), ("指标一致性", "一致性")]:
                    val = tech_struct.get(key, "")
                    if val:
                        st.markdown(f"- **{label}**: {val}")

        # 风险评估
        risk_struct = risk.get("structured", {})
        if risk_struct:
            with st.expander("风险评估", expanded=False):
                risk_level = risk_struct.get("风险等级", "")
                if risk_level:
                    level_emoji = {"低": "🟢", "中": "🟡", "高": "🔴"}.get(risk_level, "")
                    st.markdown(f"**风险等级**: {level_emoji} {risk_level}")

                factors = risk_struct.get("风险因素", [])
                if factors:
                    for f in factors:
                        st.markdown(f"- {f}")

                conflict = risk_struct.get("矛盾信号", "")
                if conflict:
                    st.markdown(f"**矛盾信号**: {conflict}")

                levels = risk_struct.get("关注点位", {})
                if levels:
                    cols = st.columns(len(levels))
                    for i, (name, value) in enumerate(levels.items()):
                        with cols[i]:
                            st.metric(name, value)

        # 操作参考 + 关注要点
        if dec_struct:
            suggestion = dec_struct.get("操作参考", "")
            if suggestion:
                st.markdown("#### 操作参考")
                st.markdown(suggestion)

            points = dec_struct.get("关注要点", [])
            if points:
                with st.expander("关注要点", expanded=False):
                    for p in points:
                        st.markdown(f"- {p}")

        st.caption(f"模型: {model_label} | 多Agent协作分析 | 不构成投资建议")


def display_ai_analysis_card(data, signals, symbol, stock_name, period):
    """AI 智能解读 — 独立区域，与交易信号平级，避免嵌套渲染"""
    st.divider()
    st.subheader("AI 智能解读")

    key = st.session_state.get("ai_api_key") or AI_API_KEY
    model = st.session_state.get("ai_model") or AI_MODEL

    if not key:
        with st.expander("设置 API Key", expanded=True):
            _show_setup_form()
        return

    # 已配置：显示 AI 分析功能
    _show_analysis_ui(data, signals, symbol, stock_name, period, key, model)

    if st.checkbox("更换配置", key=f"ai_change_cfg_{symbol}_{period}"):
        _show_setup_form(symbol, period)


def _render_analysis_results(data, signals, quote, symbol, stock_name, market, period):
    """渲染个股分析结果 — Apple×Tesla 分层布局"""
    st.markdown('<div id="analysis-results"></div>', unsafe_allow_html=True)
    st.divider()

    # ① 标题行
    col_title, col_watchlist = st.columns([3, 1])
    with col_title:
        st.markdown(f'<div style="font-size:1.25rem;font-weight:600;margin-bottom:8px;">{symbol} {stock_name}</div>', unsafe_allow_html=True)
    with col_watchlist:
        if is_in_watchlist(symbol, market):
            if st.button("移除自选", key="remove_watchlist"):
                success, msg = remove_from_watchlist(symbol, market)
                if success:
                    st.success(msg)
                    st.rerun()
        else:
            if st.button("加入自选", key="add_watchlist"):
                success, msg = add_to_watchlist(symbol, stock_name, market)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.warning(msg)

    # ② 核心指标 — 最新价 2x + 其余 1x
    if quote:
        col_price, col_h, col_l, col_v, col_o = st.columns([2, 1, 1, 1, 1])
        with col_price:
            change = quote['change']
            delta_color = "#e53935" if change >= 0 else "#2e7d32"
            delta_sign = "+" if change >= 0 else ""
            st.markdown(f'''
            <div style="background:rgba(26,115,232,0.12);border:1px solid rgba(26,115,232,0.18);
                        border-radius:12px;padding:14px 16px;box-sizing:border-box;">
              <div style="font-size:0.8rem;margin-bottom:6px;font-weight:800;color:inherit;">最新价</div>
              <div style="font-size:2.2rem;font-weight:700;line-height:1.2;">{quote["price"]:.2f}</div>
              <div style="font-size:0.95rem;font-weight:500;color:{delta_color};margin-top:4px;">{delta_sign}{change:.2f}%</div>
            </div>
            ''', unsafe_allow_html=True)
        with col_h:
            st.metric("最高", f"{quote['high']:.2f}")
        with col_l:
            st.metric("最低", f"{quote['low']:.2f}")
        with col_v:
            vol = quote['volume']
            if vol >= 1e8:
                volume = vol / 1e8
                unit = "亿"
            elif vol >= 1e4:
                volume = vol / 1e4
                unit = "万"
            else:
                volume = vol
                unit = ""
            st.metric("成交量", f"{volume:.1f}{unit}")
        with col_o:
            st.metric("今开", f"{quote['open']:.2f}")

    # ③ 分时图（仅A股）
    if market == "CN":
        intraday = get_cached_intraday_data(symbol, market)
        if intraday is not None and not intraday.empty:
            intraday_fig = plot_intraday_chart(intraday, quote)
            if intraday_fig:
                st.plotly_chart(intraday_fig, use_container_width=True,
                                config={'displayModeBar': False})

    st.divider()

    # ④ 交易信号 — 徽章横排
    display_signals(signals)

    # ⑤ AI 智能解读
    if AI_ENABLED:
        display_ai_analysis_card(data, signals, symbol, stock_name, period)

    # ⑥ K线图（复合图：价格+成交量+MACD）
    st.divider()
    plot_candlestick_chart(data)

    # ⑦ RSI + KDJ 并排（默认折叠）
    with st.expander("RSI & KDJ 指标", expanded=False):
        col_rsi, col_kdj = st.columns(2)
        with col_rsi:
            st.markdown('<p class="chart-section-title">RSI</p>', unsafe_allow_html=True)
            fig = plot_rsi_chart(data)
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        with col_kdj:
            st.markdown('<p class="chart-section-title">KDJ</p>', unsafe_allow_html=True)
            fig = plot_kdj_chart(data)
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    # ⑧ 布林带（默认折叠）
    with st.expander("布林带", expanded=False):
        fig = plot_boll_chart(data)
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    # ⑨ 原始数据（折叠）
    with st.expander("查看原始数据"):
        st.dataframe(data.tail(20))


def analyze_stock_page():
    """个股分析页面"""
    st.markdown('<h1 class="main-header">股票技术分析</h1>', unsafe_allow_html=True)

    # 使用 session state 保存查询状态 - 初始化
    if 'analyze_symbol' not in st.session_state:
        st.session_state.analyze_symbol = "000001"
    if 'analyze_market' not in st.session_state:
        st.session_state.analyze_market = "CN"
    if 'analyze_period' not in st.session_state:
        st.session_state.analyze_period = "1y"

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
        period_options = ["1wk", "1mo", "3mo", "6mo", "1y", "2y"]
        period_labels = {
            "1wk": "1周 · 短线异动",
            "1mo": "1个月 · 短线择时",
            "3mo": "3个月 · 波段确认",
            "6mo": "6个月 · 趋势判断",
            "1y": "1年 · 长线布局",
            "2y": "2年 · 历史锚点",
        }
        period_index = period_options.index(st.session_state.analyze_period)
        period = st.selectbox("时间周期", options=period_options,
                             index=period_index,
                             format_func=lambda x: period_labels[x],
                             key="analyze_period_select",
                             on_change=on_period_change)

    # 从 session state 读取当前值
    symbol = st.session_state.analyze_symbol
    market = st.session_state.analyze_market
    period = st.session_state.analyze_period

    # 配色方案选择
    if 'color_scheme' not in st.session_state:
        st.session_state.color_scheme = DEFAULT_COLOR_SCHEME.get(market, 'red_up')

    def on_color_scheme_change():
        st.session_state.color_scheme = st.session_state.color_scheme_select

    scheme_options = list(COLOR_SCHEMES.keys())
    scheme_labels = {k: v['label'] for k, v in COLOR_SCHEMES.items()}
    scheme_index = scheme_options.index(st.session_state.color_scheme)
    st.selectbox("配色方案", options=scheme_options,
                 index=scheme_index, format_func=lambda x: scheme_labels[x],
                 key="color_scheme_select", on_change=on_color_scheme_change,
                 help="红涨绿跌(A股传统) | 绿涨红跌(国际惯例) | 蓝涨橙跌(色盲友好)")

    col_analyze, col_clear = st.columns([4, 1])
    with col_clear:
        if st.button("刷新数据", type="secondary"):
            get_cached_stock_data.clear()
            get_cached_realtime_quote.clear()
            get_cached_stock_info.clear()
            st.success("已清除缓存，请重新分析")
    with col_analyze:
        analyze_clicked = st.button("开始分析", type="primary", use_container_width=True) or st.session_state.pop('trigger_analysis', False)

    # 股票代码格式校验
    def validate_symbol(sym, mkt):
        """校验股票代码格式，返回(valid, error_msg)"""
        sym = sym.strip()
        if not sym:
            return False, "请输入股票代码"
        if mkt == "CN":
            if not sym.isdigit() or len(sym) != 6:
                return False, "A股代码应为6位数字，如: 000001, 600519"
        elif mkt == "US":
            if not sym.isascii() or not sym.replace('.', '').replace('-', '').isalpha() or len(sym) > 10:
                return False, "美股代码应为纯字母，如: AAPL, TSLA, BRK.B"
        elif mkt == "HK":
            if not sym.isdigit() or len(sym) < 1 or len(sym) > 5:
                return False, "港股代码应为1-5位数字，如: 00700, 9988"
        return True, ""

    if analyze_clicked:
        is_valid, err_msg = validate_symbol(symbol, market)
        if not is_valid:
            st.error(f"输入的股票代码格式有误，{err_msg}")
            st.stop()

        # 使用进度条显示加载状态
        progress_bar = st.progress(0)
        status_text = st.empty()

        status_text.text("正在获取股票信息...")
        progress_bar.progress(5)
        info = get_cached_stock_info(symbol, market)
        progress_bar.progress(20)

        status_text.text("正在获取实时行情...")
        quote = get_cached_realtime_quote(symbol, market)
        progress_bar.progress(40)

        status_text.text("正在获取历史K线数据...")
        data = get_cached_stock_data(symbol, period, market)
        progress_bar.progress(60)

        # 调试信息
        if data is None:
            st.error(f"数据获取失败: {symbol}")
            st.error("**可能原因：**\n1. 股票代码不存在或已退市\n2. 所有数据源暂时不可用\n3. 网络连接问题")
            with st.expander("查看调试信息"):
                st.info("已尝试以下数据源：\n1. AKShare（腾讯财经）\n2. 新浪财经\n3. Yahoo Finance（仅美股/港股）")
            progress_bar.empty()
            status_text.empty()
            return
        else:
            st.write(f"获取到 {len(data)} 天数据")

        if data is None or data.empty:
            st.error(f"未能获取到 {symbol} 的数据，请检查：\n1. 股票代码是否正确\n2. 市场选择是否正确\n3. 网络连接是否正常")
            progress_bar.empty()
            status_text.empty()
            return

        # 获取数据源信息
        data_source = data.attrs.get('data_source', '未知')
        offline_mode = data.attrs.get('offline_mode', False)
        is_fallback = "AKShare" not in data_source and not offline_mode

        # 数据源标注 — 常态透明不打扰，异常温和提示
        if offline_mode:
            st.caption(f"🔴 离线缓存 · {data_source}")
        elif is_fallback:
            st.caption(f"🟡 备选数据源 · {data_source}")
        else:
            st.caption(f"数据源 · {data_source}")

        # 检查数据是否足够（至少需要30天数据）
        if len(data) < 30:
            st.warning(f"{symbol} 数据不足（仅{len(data)}天），部分指标可能无法计算")

        status_text.text("正在合并实时行情...")
        # 如果有实时行情，更新历史数据最后一行（避免同一天重复行）
        if quote and data is not None and not data.empty:
            today = pd.Timestamp.now().normalize()
            if data.index[-1].normalize() == today:
                # 更新已存在的今日行
                idx = data.index[-1]
                data.loc[idx, 'close'] = quote['price']
                data.loc[idx, 'high'] = max(data.loc[idx, 'high'], quote['high'])
                data.loc[idx, 'low'] = min(data.loc[idx, 'low'], quote['low'])
                data.loc[idx, 'volume'] = quote.get('volume', data.loc[idx, 'volume'])
            else:
                # 新交易日，追加实时行情行
                realtime_row = pd.DataFrame({
                    'open': [quote['open']],
                    'high': [quote['high']],
                    'low': [quote['low']],
                    'close': [quote['price']],
                    'volume': [quote['volume']]
                }, index=[pd.Timestamp.now()])
                data = pd.concat([data, realtime_row])
        progress_bar.progress(75)

        status_text.text("正在计算技术指标 (MACD/RSI/KDJ/BOLL/MA)...")
        data = TechnicalIndicators.calculate_all(data)
        progress_bar.progress(90)

        status_text.text("正在生成交易信号...")
        signals = TechnicalIndicators.get_signals(data)
        progress_bar.progress(100)

        # 检查是否有错误
        if 'error' in signals:
            st.warning(f"指标计算问题：{signals['error']}")

        # 清除进度条
        progress_bar.empty()
        status_text.empty()

        # 获取股票名称并保存分析结果到 session_state
        stock_name = fetcher.get_stock_name(symbol, market)

        st.session_state.analyzed_data = data
        st.session_state.analyzed_signals = signals
        st.session_state.analyzed_quote = quote
        st.session_state.analyzed_stock_name = stock_name

        # 渲染分析结果
        _render_analysis_results(data, signals, quote, symbol, stock_name, market, period)

    # rerun 恢复：st.rerun() 后 analyze_clicked=False，从 session_state 恢复全部结果
    if not analyze_clicked:
        cached_data = st.session_state.get("analyzed_data")
        if cached_data is not None:
            _render_analysis_results(
                cached_data,
                st.session_state.get("analyzed_signals", {}),
                st.session_state.get("analyzed_quote"),
                symbol,
                st.session_state.get("analyzed_stock_name", ""),
                market,
                period
            )

    # 锚点滚动：分析完成后滚动到结果区
    if st.session_state.pop('scroll_to_results', False):
        st.components.v1.html("""
        <script>
            var el = parent.document.getElementById('analysis-results');
            if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
        </script>
        """, height=0)


@st.cache_data(ttl=CACHE_TTL_HOT_STOCKS, show_spinner=False)
def get_cached_hot_stocks(market):
    """缓存热门股票数据"""
    recommender = StockRecommender()
    if market == "CN":
        return {
            'hot': recommender.get_hot_stocks_cn(limit=20),
            'gainers': recommender.get_top_gainers_cn(limit=10),
            'losers': recommender.get_top_losers_cn(limit=10),
            'sectors': recommender.get_hot_sectors_cn(limit=30)
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

    # 使用 session state 保存热门股票页面状态
    if 'hot_market' not in st.session_state:
        st.session_state.hot_market = "CN"

    def on_hot_market_change():
        st.session_state.hot_market = st.session_state.hot_market_select
        st.session_state.hot_data_loaded = False  # 市场切换时重新加载

    market_index = ["CN", "US", "HK"].index(st.session_state.hot_market) if st.session_state.hot_market in ["CN", "US", "HK"] else 0
    market = st.selectbox("选择市场", options=["CN", "US", "HK"],
                         index=market_index,
                         format_func=lambda x: {"CN": "A股", "US": "美股", "HK": "港股"}[x],
                         key="hot_market_select",
                         on_change=on_hot_market_change)

    market = st.session_state.hot_market

    # 自动加载数据（首次进入或市场切换后）
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
            gainers = data.get('gainers', [])
            losers = data.get('losers', [])

            # 热门板块（同花顺行业板块排行）
            st.subheader("行业板块排行")
            if sectors:
                df_sectors = pd.DataFrame(sectors)
                # 涨跌幅着色
                def color_change(val):
                    if val > 0:
                        return 'color: #e53935'
                    elif val < 0:
                        return 'color: #2e7d32'
                    return ''
                df_styled = df_sectors.style.map(color_change, subset=['涨跌幅', '领涨股涨幅'])
                st.dataframe(df_styled, use_container_width=True, hide_index=True)
            else:
                st.info("暂无板块数据")

            # 涨幅榜
            st.subheader("个股涨幅榜")
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
            st.subheader("个股跌幅榜")
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

def display_recommendation_list(recommended, strategy_name):
    """显示推荐列表"""
    if not recommended:
        st.warning(f"暂无{strategy_name}推荐股票")
        st.info("可能原因：\n1. 数据获取失败（网络问题）\n2. 股票分析返回None（数据不足）\n3. 请检查日志输出")
        return

    st.success(f"{strategy_name}：为您推荐以下 {len(recommended)} 只股票")

    # 显示推荐列表
    for i, stock in enumerate(recommended, 1):
        with st.container():
            st.markdown(f"""
            <div class="stock-card">
                <h4>#{i} {html.escape(str(stock['symbol']))} {html.escape(str(stock['name']))}</h4>
                <p><strong>综合评分:</strong> {stock['score']}/100 |
                <strong>建议:</strong> {html.escape(str(stock['rating']))} |
                <strong>当前价:</strong> {stock['latest_price']:.2f}</p>
            </div>
            """, unsafe_allow_html=True)

            # 显示详细指标
            cols = st.columns(4)
            with cols[0]:
                st.markdown(f'<p style="font-size:1.05rem;margin:0"><b>MACD:</b> {stock["indicators"]["macd"]:.2f}</p>', unsafe_allow_html=True)
                st.markdown(f'<p style="font-size:0.95rem;margin:0;opacity:0.85">{html.escape(stock["signals"]["macd"])}</p>', unsafe_allow_html=True)
            with cols[1]:
                st.markdown(f'<p style="font-size:1.05rem;margin:0"><b>RSI:</b> {stock["indicators"]["rsi"]:.2f}</p>', unsafe_allow_html=True)
                st.markdown(f'<p style="font-size:0.95rem;margin:0;opacity:0.85">{html.escape(stock["signals"]["rsi"])}</p>', unsafe_allow_html=True)
            with cols[2]:
                st.markdown(f'<p style="font-size:1.05rem;margin:0"><b>KDJ:</b> K:{stock["indicators"]["kdj_k"]:.2f} D:{stock["indicators"]["kdj_d"]:.2f}</p>', unsafe_allow_html=True)
                st.markdown(f'<p style="font-size:0.95rem;margin:0;opacity:0.85">{html.escape(stock["signals"]["kdj"])}</p>', unsafe_allow_html=True)
            with cols[3]:
                boll_lower = stock['indicators'].get('boll_lower', 0)
                boll_upper = stock['indicators'].get('boll_upper', 0)
                st.markdown(f'<p style="font-size:1.05rem;margin:0"><b>布林带:</b> {boll_lower:.2f}-{boll_upper:.2f}</p>', unsafe_allow_html=True)
                st.markdown(f'<p style="font-size:0.95rem;margin:0;opacity:0.85">{html.escape(stock["signals"]["boll"])}</p>', unsafe_allow_html=True)

            st.divider()

def recommended_stocks_page():
    """推荐股票页面 - 短线龙头股推荐"""
    st.markdown('<h1 class="main-header">短线龙头股推荐</h1>', unsafe_allow_html=True)

    # 使用 session state 保存推荐页面状态
    if 'rec_sector' not in st.session_state:
        st.session_state.rec_sector = "全部"
    if 'rec_num_stocks' not in st.session_state:
        st.session_state.rec_num_stocks = 5

    def on_sector_change():
        st.session_state.rec_sector = st.session_state.rec_sector_select
        st.session_state.rec_data_loaded = False  # 板块切换时重新加载

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

    # 自动加载数据（首次进入时）
    if 'rec_data_loaded' not in st.session_state:
        st.session_state.rec_data_loaded = False

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("刷新数据", type="secondary"):
            st.session_state.rec_data_loaded = False
            st.success("数据已刷新")

    if st.button("生成推荐", type="primary") or not st.session_state.rec_data_loaded:
        with st.spinner(f"正在分析{sector}板块，请稍候..."):
            recommender = StockRecommender()
            if sector == "全部":
                recommended = recommender.get_short_term_recommendations(num_stocks)
                st.caption(f"分析完成：找到 {len(recommended)} 只推荐股票")
                display_recommendation_list(recommended, "短线推荐")
            else:
                recommended = recommender.get_sector_short_term_recommendations(sector, num_stocks)
                st.caption(f"分析完成：找到 {len(recommended)} 只推荐股票")
                display_recommendation_list(recommended, f"{sector} 短线龙头股")
            st.session_state.rec_data_loaded = True

def display_market_temperature():
    """侧边栏大盘温度卡片 — 上证/深证/创业板实时涨跌"""
    from config import INDEX_CACHE_TTL

    @st.cache_data(ttl=INDEX_CACHE_TTL, show_spinner=False)
    def _fetch_indices():
        results = []
        for code, name in INDEX_WATCHLIST:
            quote = fetcher.get_index_realtime(code)
            if quote:
                results.append(quote)
        return results

    indices = _fetch_indices()
    if not indices:
        return

    rows = []
    for idx in indices:
        pct = idx['change_pct']
        direction = "🟢" if pct > 0 else ("🔴" if pct < 0 else "⚪")
        color = "var(--color-rise)" if pct >= 0 else "var(--color-fall)"
        rows.append(
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:3px 0;font-size:0.92rem">'
            f'<span style="opacity:0.85">{idx["name"]}</span>'
            f'<span><b>{idx["price"]:.2f}</b> '
            f'<span style="color:{color}">{direction} {pct:+.2f}%</span></span>'
            f'</div>'
        )

    st.markdown(
        f'<div style="margin:12px 0;padding:10px 12px;border-radius:10px;'
        f'background:rgba(128,128,128,0.06)">'
        f'<div style="font-size:0.8rem;opacity:0.6;margin-bottom:6px">大盘温度</div>'
        f'{"".join(rows)}'
        f'</div>',
        unsafe_allow_html=True
    )


@st.cache_data(ttl=300, show_spinner="加载自选股信号...")
def _cached_watchlist_summary(_watchlist_hash):
    """获取自选股技术摘要（带缓存，5分钟有效）"""
    watchlist = get_watchlist()
    if not watchlist:
        return []
    return get_watchlist_summary(watchlist)


def display_watchlist_sidebar():
    """在侧边栏显示自选股列表 — 含实时信号和入场提示"""
    import json as _json_for_hash

    watchlist = get_watchlist()

    with st.expander("自选股"):
        if not watchlist:
            st.caption("暂无自选股")
            return None

        # 生成缓存键（自选股变动时自动失效）
        watchlist_hash = _json_for_hash.dumps(
            [(item['symbol'], item['market']) for item in watchlist],
            sort_keys=True
        )

        with st.spinner(""):
            summaries = _cached_watchlist_summary(watchlist_hash)

        if not summaries:
            # 缓存未命中或加载中，回退到基本按钮模式
            for item in watchlist:
                col1, col2 = st.columns([4, 1])
                with col1:
                    display_text = f"{item['symbol']}"
                    if item['name'] and item['name'] != item['symbol']:
                        display_text += f" · {item['name'][:4]}"
                    if st.button(display_text, key=f"wl_{item['symbol']}_{item['market']}", use_container_width=True):
                        st.session_state.wl_view_symbol = item['symbol']
                        st.session_state.wl_view_market = item['market']
                with col2:
                    if st.button("✕", key=f"del_{item['symbol']}_{item['market']}", help="移除"):
                        remove_from_watchlist(item['symbol'], item['market'])
                        st.rerun()
            return None

        # 增强模式：显示信号 + 入场提示
        for i, item in enumerate(summaries):
            symbol = item['symbol']
            name = item.get('name', symbol)
            market = item.get('market', 'CN')
            error = item.get('error')

            # 卡片容器
            with st.container(border=True):
                # 第一行：名称 + 价格 + 删除按钮
                col_title, col_price, col_del = st.columns([2.5, 2, 0.8])
                with col_title:
                    st.markdown(f'<span style="font-weight:600">{symbol}</span> · {name[:6]}',
                               unsafe_allow_html=True)
                with col_price:
                    if item['price'] is not None:
                        change = item.get('change_pct', 0) or 0
                        color = "#e53935" if change >= 0 else "#2e7d32"
                        arrow = "+" if change >= 0 else ""
                        st.markdown(f'<span style="color:{color};font-weight:600">{arrow}{change:.2f}%</span> '
                                   f'<span style="font-size:0.85rem">¥{item["price"]:.2f}</span>',
                                   unsafe_allow_html=True)

                with col_del:
                    if st.button("✕", key=f"wldel_{symbol}_{market}_{i}", help="移除"):
                        remove_from_watchlist(symbol, market)
                        st.rerun()

                # 第二行：信号徽章 + 入场提示
                if error:
                    st.caption(f"⚠ {error}")
                else:
                    signal_text = item.get('signal_summary', '--')
                    hint_text = item.get('entry_hint', '--')

                    # 信号分类
                    if "金叉" in str(signal_text) or "超卖" in str(signal_text) or "反弹" in str(signal_text) or "偏多" in str(signal_text):
                        cls = "buy"
                    elif "死叉" in str(signal_text) or "超买" in str(signal_text) or "回调" in str(signal_text) or "偏空" in str(signal_text):
                        cls = "sell"
                    else:
                        cls = "neutral"

                    st.markdown(
                        f'<span class="signal-badge {cls}" style="font-size:0.75rem">{html.escape(str(signal_text))}</span> '
                        f'<span style="font-size:0.75rem;color:var(--text-color-secondary)">{html.escape(str(hint_text))}</span>',
                        unsafe_allow_html=True
                    )

                # 点击跳转到个股分析
                if st.button("查看分析", key=f"wlview_{symbol}_{market}_{i}", use_container_width=True):
                    st.session_state.wl_view_symbol = symbol
                    st.session_state.wl_view_market = market

    return summaries


@st.cache_data(ttl=300, show_spinner=False)
def _cached_mini_analysis(symbol, market):
    """获取单只股票简要分析数据（侧边栏 mini 面板用，5分钟缓存）"""
    from watchlist import get_watchlist_summary
    results = get_watchlist_summary([{'symbol': symbol, 'name': symbol, 'market': market}])
    return results[0] if results else None


def display_watchlist_mini_panel(summaries):
    """在侧边栏显示选中自选股的 mini 分析面板"""
    symbol = st.session_state.get('wl_view_symbol')
    market = st.session_state.get('wl_view_market')

    if not symbol:
        return

    # 优先从已有 summaries 中查找（免费），否则走缓存
    result = None
    if summaries:
        for s in summaries:
            if s['symbol'] == symbol and s['market'] == market:
                result = s
                break

    if result is None:
        result = _cached_mini_analysis(symbol, market)

    if result is None:
        return

    error = result.get('error')
    price = result.get('price')
    change_pct = result.get('change_pct', 0) or 0
    signal_text = result.get('signal_summary', '--')
    hint_text = result.get('entry_hint', '--')
    indicators = result.get('indicators', {})
    name = result.get('name', symbol)

    # 关闭按钮
    col_close = st.columns([6, 1])
    with col_close[1]:
        if st.button("✕", key="wl_mini_close", help="关闭"):
            st.session_state.wl_view_symbol = None
            st.session_state.wl_view_market = None
            st.rerun()

    # 卡片容器
    with st.container(border=True):
        # 标题行：代码 + 名称 + 价格 + 涨跌
        if error:
            st.caption(f"⚠ {error}")
            return

        change_color = "#e53935" if change_pct >= 0 else "#2e7d32"
        arrow_sign = "+" if change_pct >= 0 else ""
        st.markdown(
            f'<span style="font-weight:600">{symbol}</span> · {name[:6]}'
            f'&nbsp;&nbsp;<span style="color:{change_color};font-weight:600">¥{price:.2f} {arrow_sign}{change_pct:.2f}%</span>',
            unsafe_allow_html=True
        )

        st.divider()

        # 信号徽章
        if "金叉" in str(signal_text) or "超卖" in str(signal_text) or "反弹" in str(signal_text) or "偏多" in str(signal_text):
            cls = "buy"
        elif "死叉" in str(signal_text) or "超买" in str(signal_text) or "回调" in str(signal_text) or "偏空" in str(signal_text):
            cls = "sell"
        else:
            cls = "neutral"

        st.markdown(
            f'<span class="signal-badge {cls}" style="font-size:0.75rem">{html.escape(str(signal_text))}</span>',
            unsafe_allow_html=True
        )

        # 关键指标
        ind_lines = []
        rsi = indicators.get('rsi')
        if rsi is not None:
            ind_lines.append(f"RSI: {rsi:.1f}")

        macd = indicators.get('macd')
        macd_signal = indicators.get('macd_signal')
        if macd is not None and macd_signal is not None:
            macd_status = "金叉" if macd > macd_signal else "死叉"
            ind_lines.append(f"MACD: {macd_status}")

        k, d, j = indicators.get('kdj_k'), indicators.get('kdj_d'), indicators.get('kdj_j')
        if k is not None and d is not None and j is not None:
            ind_lines.append(f"KDJ: K{k:.1f} D{d:.1f} J{j:.1f}")

        boll_upper = indicators.get('boll_upper')
        boll_lower = indicators.get('boll_lower')
        boll_mid = indicators.get('boll_mid')
        if boll_upper is not None and boll_lower is not None and price is not None:
            band_range = boll_upper - boll_lower
            if band_range > 0:
                pos = (price - boll_lower) / band_range
                if pos <= 0.05:
                    boll_pos = "下轨附近"
                elif pos <= 0.35:
                    boll_pos = "偏下区间"
                elif pos <= 0.65:
                    boll_pos = "中轨附近"
                elif pos <= 0.95:
                    boll_pos = "偏上区间"
                else:
                    boll_pos = "上轨附近"
                ind_lines.append(f"布林: {boll_pos}")

        if ind_lines:
            st.caption("  |  ".join(ind_lines))

        # 入场提示
        if hint_text and hint_text != '--':
            st.caption(f"入场: {hint_text}")

        # 在主页查看完整分析
        if st.button("在主页查看完整分析 →", key="wl_mini_full", use_container_width=True):
            st.session_state.analyze_symbol = symbol
            st.session_state.analyze_market = market
            st.session_state.trigger_analysis = True
            st.session_state.scroll_to_results = True
            st.session_state.wl_view_symbol = None
            st.session_state.wl_view_market = None
            st.rerun()


def display_data_source_selector():
    """数据源设置（含简要说明）"""
    with st.expander("数据源"):
        current_source = fetcher.get_preferred_source()

        source_options = {
            'auto': '自动选择（推荐）',
            'akshare': 'AKShare（腾讯财经）',
            'sina': '新浪财经',
        }

        selected = st.selectbox(
            "优先数据源（A股）",
            options=list(source_options.keys()),
            index=list(source_options.keys()).index(current_source) if current_source in source_options else 0,
            format_func=lambda x: source_options[x]
        )

        if selected != current_source:
            fetcher.set_preferred_source(selected)
            st.success(f"已切换到: {source_options[selected]}")
            st.info("请重新获取数据以生效")

        with st.expander("查看详情"):
            st.markdown("""
            **A股** — AKShare（腾讯财经）→ 新浪财经 → 离线缓存

            **美股** — 新浪财经（实时 + 日K）

            **港股** — 新浪（实时）+ Yahoo（日K）

            实时行情延迟 3~5 秒，历史日K收盘后更新
            """)


def compare_stocks_page():
    """股票对比页面"""
    st.markdown('<h1 class="main-header">股票对比</h1>', unsafe_allow_html=True)

    st.info("同时对比多只股票的关键指标，最多支持5只股票（并发获取，速度更快）")

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

    if st.button("开始对比", type="primary"):
        symbols = [s.strip() for s in symbols_input.strip().split('\n') if s.strip()][:5]

        if len(symbols) < 2:
            st.warning("请至少输入2只股票进行对比")
            return

        with st.spinner(f"正在并发获取 {len(symbols)} 只股票数据..."):
            # 使用并发获取加速
            from data_fetcher import StockDataFetcher

            progress_bar = st.progress(0)
            status_text = st.empty()

            # 准备股票列表
            stocks_to_fetch = [{'code': s, 'name': s} for s in symbols]

            status_text.text("并发获取股票数据...")
            results = StockDataFetcher.fetch_multiple_stocks(
                stocks_to_fetch, period='3mo', market=market, max_workers=5
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

                        # 计算涨跌幅
                        change_pct = ((latest['close'] - data.iloc[0]['close']) / data.iloc[0]['close']) * 100

                        comparison_data.append({
                            '代码': symbol,
                            '名称': fetcher.get_stock_name(symbol, market),
                            '最新价': f"{latest['close']:.2f}",
                            '涨跌幅': f"{change_pct:.2f}%",
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
                # 显示对比表格
                df = pd.DataFrame(comparison_data)
                st.subheader("关键指标对比")
                st.dataframe(df, use_container_width=True)

                # 显示价格走势图对比
                st.subheader("价格走势对比")
                fig = go.Figure()

                for symbol in symbols:
                    result = results.get(symbol)
                    if result and result['success']:
                        try:
                            data = result['data']
                            # 标准化价格（以第一天为基准100）
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


def main():
    """主函数"""
    # 侧边栏导航
    with st.sidebar:
        st.title("股票分析系统")
        st.markdown("---")

        _nav_emoji = {"个股分析": "📈", "热门板块": "🔥", "智能推荐": "💡", "股票对比": "📊", "回测验证": "⏮"}
        page = st.radio(
            "功能菜单",
            options=["个股分析", "热门板块", "智能推荐", "股票对比", "回测验证"],
            format_func=lambda x: f"{_nav_emoji.get(x, '')} {x}"
        )

        # 大盘温度（默认关闭，环境变量 MARKET_INDEX_ENABLED=true 开启）
        if MARKET_INDEX_ENABLED:
            display_market_temperature()

        # 自选股（折叠）
        summaries = display_watchlist_sidebar()

        # 侧边栏 mini 分析面板（查看自选股时显示）
        display_watchlist_mini_panel(summaries)

        # 数据源
        display_data_source_selector()

        st.caption("风险提示：本系统仅供参考，不构成投资建议")

    # 页面路由
    if page == "个股分析":
        analyze_stock_page()
    elif page == "热门板块":
        hot_stocks_page()
    elif page == "智能推荐":
        recommended_stocks_page()
    elif page == "股票对比":
        compare_stocks_page()
    elif page == "回测验证":
        from backtest_ui import backtest_page
        backtest_page()

if __name__ == "__main__":
    main()
