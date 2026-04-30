"""
股票分析系统 - Web版本 (优化版)
使用Streamlit构建，带缓存加速
"""
import streamlit as st
import pandas as pd
import numpy as np
import html
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 导入原有模块
from data_fetcher import StockDataFetcher, CN_STOCK_NAMES_EXTENDED, POPULAR_CN_STOCKS
from technical_indicators import TechnicalIndicators
from stock_recommendation import StockRecommender
from watchlist import add_to_watchlist, remove_from_watchlist, get_watchlist, is_in_watchlist
from config import (
    CACHE_TTL_REALTIME, CACHE_TTL_STOCK_DATA, CACHE_TTL_STOCK_INFO,
    CACHE_TTL_HOT_STOCKS, CACHE_TTL_INDICATORS,
    CACHE_TTL_RECOMMENDED, CACHE_TTL_SHORT_TERM, CACHE_TTL_SECTOR,
    RSI_OVERBOUGHT, RSI_OVERSOLD, KDJ_OVERBOUGHT, KDJ_OVERSOLD,
    DEFAULT_COLOR_SCHEME, COLOR_SCHEMES,
    AI_ENABLED, AI_MODEL, AI_API_KEY, AI_BASE_URL, AI_TEMPERATURE,
    AI_CACHE_TTL_SECONDS,
)
from ai_analysis import build_indicator_snapshot, call_ai_analysis
from chart_utils import resolve_color_scheme, get_volume_colors, get_macd_hist_colors, MA_CONFIG

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

# 页面配置
st.set_page_config(
    page_title="股票分析系统",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义CSS样式 — 苹果极简风（暗色/亮色主题兼容：使用半透明色和继承色）
st.markdown("""
<style>
    /* ===== 全局字体 ===== */
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    }

    /* ===== 等宽数字 — 金融数据列对齐 ===== */
    [data-testid="stMetricValue"], [data-testid="stDataFrame"] td {
        font-feature-settings: "tnum";
        font-variant-numeric: tabular-nums;
    }

    /* ===== 极简标题 ===== */
    .main-header {
        font-size: 2rem;
        font-weight: 600;
        letter-spacing: -0.025em;
        color: inherit;
        margin-bottom: 1.5rem;
    }

    /* ===== 信号：仅颜色区分，微加粗 ===== */
    .buy-signal  { color: #cc0000; font-weight: 500; }
    .sell-signal { color: #008844; font-weight: 500; }
    .neutral-signal { opacity: 0.5; }

    /* ===== 极简卡片 + 悬停动效 ===== */
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
        border-radius: 8px;
        padding: 0.5rem;
        margin: 0.25rem 0;
        transition: background 0.2s ease;
    }
    .watchlist-item:hover {
        background: rgba(128, 128, 128, 0.08);
    }

    /* ===== 按钮：苹果风格圆角 ===== */
    .stButton button {
        border-radius: 12px !important;
        font-weight: 500;
        border: none;
        transition: all 0.15s ease;
    }

    /* ===== 主按钮：深灰代替蓝色 ===== */
    .stButton button[kind="primary"] {
        background-color: #333;
        color: #fff;
    }
    .stButton button[kind="secondary"] {
        background-color: rgba(128, 128, 128, 0.1);
        color: inherit;
    }

    /* ===== 侧边栏 ===== */
    [data-testid="stSidebar"] {
        background-color: rgba(128, 128, 128, 0.02);
    }

    /* ===== 侧边栏 Radio 导航 ===== */
    [data-testid="stSidebar"] .stRadio label {
        padding: 0.4rem 0.75rem;
        border-radius: 10px;
        transition: background 0.2s ease;
    }

    /* ===== 侧边栏分隔线更紧凑 ===== */
    [data-testid="stSidebar"] hr {
        margin: 0.8rem 0;
        opacity: 0.2;
    }

    /* ===== Metric 指标卡片 — 特斯拉风格大数字 ===== */
    [data-testid="stMetric"] {
        background: rgba(128, 128, 128, 0.03);
        border-radius: 12px;
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

    /* ===== Tab 标签 ===== */
    .stTabs [role="tab"] {
        font-weight: 500;
        border-radius: 10px;
        transition: background 0.2s ease;
    }

    /* ===== DataFrame 表格 ===== */
    [data-testid="stDataFrame"] {
        border-radius: 12px;
        overflow: hidden;
    }
    [data-testid="stDataFrame"] table {
        border-radius: 12px;
    }
    [data-testid="stDataFrame"] th {
        font-weight: 500;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        opacity: 0.6;
    }

    /* ===== Expander 折叠面板 ===== */
    [data-testid="stExpander"] {
        border-radius: 12px;
        border: none !important;
    }

    /* ===== SelectBox / TextInput 圆角 ===== */
    [data-testid="stTextInput"] input,
    [data-testid="stSelectbox"] div[role="combobox"],
    .stSelectbox [data-baseweb="select"] {
        border-radius: 10px !important;
    }

    /* ===== Divider 分隔线更淡 ===== */
    hr {
        opacity: 0.3;
        margin: 1.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

def plot_candlestick_chart(data, title="K线图"):
    """使用Plotly绘制K线图"""
    scheme_name = st.session_state.get('color_scheme')
    market = st.session_state.get('analyze_market', 'CN')
    colors = resolve_color_scheme(scheme_name, market)
    inc_color = colors['increasing']
    dec_color = colors['decreasing']

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
            increasing_line_color=inc_color,
            decreasing_line_color=dec_color
        ),
        row=1, col=1
    )

    # 移动平均线
    for ma_conf in MA_CONFIG.values():
        col_name = f'ma{ma_conf["period"]}'
        if col_name in data.columns:
            fig.add_trace(go.Scatter(x=data.index, y=data[col_name], name=ma_conf['label'],
                                     line=dict(color=ma_conf['color'], width=1)), row=1, col=1)

    # 成交量
    if 'volume' in data.columns:
        vol_colors = get_volume_colors(data, inc_color, dec_color)
        fig.add_trace(
            go.Bar(x=data.index, y=data['volume'], name='成交量', marker_color=vol_colors),
            row=2, col=1
        )

    # MACD
    if 'macd' in data.columns:
        fig.add_trace(go.Scatter(x=data.index, y=data['macd'], name='DIF', line=dict(color='blue')), row=3, col=1)
        fig.add_trace(go.Scatter(x=data.index, y=data['macd_signal'], name='DEA', line=dict(color='red')), row=3, col=1)

        # MACD柱状图
        colors_macd = get_macd_hist_colors(data['macd_hist'], inc_color, dec_color)
        fig.add_trace(
            go.Bar(x=data.index, y=data['macd_hist'], name='MACD', marker_color=colors_macd),
            row=3, col=1
        )

        # 金叉/死叉标记
        macd_vals = data['macd'].values
        signal_vals = data['macd_signal'].values
        golden_idx = np.where((macd_vals > signal_vals) & (np.roll(macd_vals <= signal_vals, 1)))[0]
        death_idx = np.where((macd_vals < signal_vals) & (np.roll(macd_vals >= signal_vals, 1)))[0]
        # 排除第一个元素（roll导致的不真实交叉）
        golden_idx = golden_idx[golden_idx > 0]
        death_idx = death_idx[death_idx > 0]
        if len(golden_idx) > 0:
            fig.add_trace(go.Scatter(
                x=data.index[golden_idx], y=data['macd'].iloc[golden_idx],
                mode='markers', name='MACD金叉', marker=dict(symbol='triangle-up', size=12, color=inc_color, line=dict(width=1)),
                showlegend=True, hovertemplate='金叉<br>%{x}<br>MACD: %{y:.4f}'), row=3, col=1)
        if len(death_idx) > 0:
            fig.add_trace(go.Scatter(
                x=data.index[death_idx], y=data['macd'].iloc[death_idx],
                mode='markers', name='MACD死叉', marker=dict(symbol='triangle-down', size=12, color=dec_color, line=dict(width=1)),
                showlegend=True, hovertemplate='死叉<br>%{x}<br>MACD: %{y:.4f}'), row=3, col=1)

    fig.update_layout(
        title=title,
        xaxis_rangeslider_visible=False,
        height=800,
        showlegend=True,
        hovermode='x unified',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_family='-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif',
        margin=dict(l=20, r=20, t=40, b=20)
    )

    fig.update_xaxes(rangeslider_visible=False)
    fig.update_yaxes(title_text="价格", row=1, col=1)
    fig.update_yaxes(title_text="成交量", row=2, col=1)
    fig.update_yaxes(title_text="MACD", row=3, col=1)

    return fig

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

    fig.update_layout(
        title="RSI指标 (6日/12日/24日)",
        height=400,
        yaxis_range=[0, 100],
        hovermode='x unified',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_family='-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif',
        margin=dict(l=20, r=20, t=40, b=20)
    )

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

    fig.update_layout(
        title="KDJ指标 (随机指标)",
        height=400,
        hovermode='x unified',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_family='-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif',
        margin=dict(l=20, r=20, t=40, b=20)
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
        hovermode='x unified',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_family='-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif',
        margin=dict(l=20, r=20, t=40, b=20)
    )

    return fig

def display_signals(signals):
    """显示交易信号"""
    # 处理错误情况
    if 'error' in signals:
        st.warning(f"{signals['error']}")
        return

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.subheader("MACD")
        macd_signal = signals.get('macd', '暂无数据')
        if "金叉" in macd_signal:
            st.markdown(f"<span class='buy-signal'>{macd_signal}</span>", unsafe_allow_html=True)
        elif "死叉" in macd_signal:
            st.markdown(f"<span class='sell-signal'>{macd_signal}</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span class='neutral-signal'>{macd_signal}</span>", unsafe_allow_html=True)

    with col2:
        st.subheader("RSI")
        rsi_signal = signals.get('rsi', '暂无数据')
        if "超卖" in rsi_signal:
            st.markdown(f"<span class='buy-signal'>{rsi_signal}</span>", unsafe_allow_html=True)
        elif "超买" in rsi_signal:
            st.markdown(f"<span class='sell-signal'>{rsi_signal}</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span class='neutral-signal'>{rsi_signal}</span>", unsafe_allow_html=True)

    with col3:
        st.subheader("KDJ")
        kdj_signal = signals.get('kdj', '暂无数据')
        if "金叉" in kdj_signal or "超卖" in kdj_signal:
            st.markdown(f"<span class='buy-signal'>{kdj_signal}</span>", unsafe_allow_html=True)
        elif "死叉" in kdj_signal or "超买" in kdj_signal:
            st.markdown(f"<span class='sell-signal'>{kdj_signal}</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span class='neutral-signal'>{kdj_signal}</span>", unsafe_allow_html=True)

    with col4:
        st.subheader("布林带")
        boll_signal = signals.get('boll', '暂无数据')
        if "反弹" in boll_signal or "偏多" in boll_signal:
            st.markdown(f"<span class='buy-signal'>{boll_signal}</span>", unsafe_allow_html=True)
        elif "回调" in boll_signal or "偏空" in boll_signal:
            st.markdown(f"<span class='sell-signal'>{boll_signal}</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span class='neutral-signal'>{boll_signal}</span>", unsafe_allow_html=True)

    # 综合建议
    st.divider()
    recommendation = signals.get('recommendation', '观望')

    # 汇总各指标理由
    reasons = []
    macd_sig = signals.get('macd', '')
    if "金叉" in macd_sig:
        reasons.append(f"MACD {macd_sig}")
    elif "死叉" in macd_sig:
        reasons.append(f"MACD {macd_sig}")

    rsi_sig = signals.get('rsi', '')
    if "超买" in rsi_sig:
        reasons.append(f"RSI {rsi_sig}")
    elif "超卖" in rsi_sig:
        reasons.append(f"RSI {rsi_sig}")

    kdj_sig = signals.get('kdj', '')
    if "金叉" in kdj_sig:
        reasons.append(f"KDJ {kdj_sig}")
    elif "死叉" in kdj_sig:
        reasons.append(f"KDJ {kdj_sig}")
    elif "超买" in kdj_sig or "超卖" in kdj_sig:
        reasons.append(f"KDJ {kdj_sig}")

    boll_sig = signals.get('boll', '')
    if "反弹" in boll_sig or "回调" in boll_sig:
        reasons.append(f"BOLL {boll_sig}")

    reason_text = "；".join(reasons) if reasons else "各指标均处于中性区间"

    if "偏多" in recommendation:
        st.success(f"### 综合建议: {recommendation}")
        st.caption(f"判断依据：{reason_text}")
    elif "偏空" in recommendation:
        st.error(f"### 综合建议: {recommendation}")
        st.caption(f"判断依据：{reason_text}")
    else:
        st.info(f"### 综合建议: {recommendation}")
        st.caption(f"判断依据：{reason_text}")


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

    if cache_key not in st.session_state:
        st.session_state[cache_key] = None

    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        if st.button("AI 分析", type="primary", key=f"ai_btn_{symbol}_{period}"):
            error_msg = None
            try:
                with st.spinner("AI 正在分析技术指标..."):
                    snapshot = build_indicator_snapshot(data, signals, symbol, stock_name)
                    result = call_ai_analysis(
                        snapshot, model, api_key, AI_BASE_URL, AI_TEMPERATURE
                    )
                    st.session_state[cache_key] = result
            except Exception as e:
                st.session_state[cache_key] = None
                error_msg = str(e)
            if error_msg:
                st.error(f"分析失败：{error_msg}")
            else:
                st.rerun()
    with col_info:
        model_label = AI_MODEL_OPTIONS.get(model, model)
        st.caption(f"当前模型: {model_label}")

    result = st.session_state[cache_key]
    if result:
        st.markdown("#### 核心结论")
        st.markdown(result.get("核心结论", "无"))

        risks = result.get("风险提示", [])
        if risks:
            st.markdown("#### 风险提示")
            for r in risks:
                st.markdown(f"- {r}")

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
            st.markdown(suggestion)

        st.caption(f"模型: {model_label} | 以上为 AI 自动分析，不构成投资建议")


def display_ai_analysis_card(data, signals, symbol, stock_name, period):
    """AI 智能解读卡片 — 配置入口 + 分析功能"""
    with st.expander("AI 智能解读", expanded=False):
        key = st.session_state.get("ai_api_key") or AI_API_KEY
        model = st.session_state.get("ai_model") or AI_MODEL

        if key:
            _show_analysis_ui(data, signals, symbol, stock_name, period, key, model)
            if st.checkbox("更换配置", key=f"ai_change_cfg_{symbol}_{period}"):
                _show_setup_form(symbol, period)
        else:
            _show_setup_form()


def _render_analysis_results(data, signals, quote, symbol, stock_name, market, period):
    """渲染个股分析结果（从 session_state 恢复或首次显示）"""
    st.divider()

    # 股票标题 + 自选股按钮
    col_title, col_watchlist = st.columns([3, 1])
    with col_title:
        st.header(f"{symbol} {stock_name}")
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
        with cols[4]:
            st.metric("今开", f"{quote['open']:.2f}")

    st.divider()

    # 交易信号
    display_signals(signals)

    # AI 智能解读
    if AI_ENABLED:
        display_ai_analysis_card(data, signals, symbol, stock_name, period)

    st.divider()

    # 指标数值
    latest = data.iloc[-1]
    cols = st.columns(4)

    with cols[0]:
        st.subheader("MACD")
        st.write(f"DIF: {latest['macd']:.2f}")
        st.write(f"DEA: {latest['macd_signal']:.2f}")
        st.write(f"MACD: {latest['macd_hist']:.2f}")

    with cols[1]:
        st.subheader("RSI")
        st.write(f"RSI(6): {latest['rsi_6']:.2f}")
        st.write(f"RSI(12): {latest['rsi_12']:.2f}")
        st.write(f"RSI(24): {latest['rsi_24']:.2f}")

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

    # 图表
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

    # 原始数据
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
        period_options = ["1mo", "3mo", "6mo", "1y"]
        period_labels = {"1mo": "1个月", "3mo": "3个月", "6mo": "6个月", "1y": "1年"}
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
        analyze_clicked = st.button("开始分析", type="primary", use_container_width=True)

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
                st.info("已尝试以下数据源：\n1. AKShare (同花顺/东方财富)\n2. 新浪财经\n3. Yahoo Finance")
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

        # 显示数据源信息
        if offline_mode:
            st.error(f"离线模式 | 数据源: {data_source} | 网络异常，显示缓存数据")
        elif is_fallback:
            st.warning(f"当前数据源: {data_source} | 同花顺数据源暂不可用，正在使用备选数据源")
        else:
            st.success(f"数据源: {data_source}")

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
                        return 'color: #cc0000'
                    elif val < 0:
                        return 'color: #008844'
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

@st.cache_data(ttl=CACHE_TTL_RECOMMENDED, show_spinner=False)
def get_cached_recommended_stocks(num_stocks):
    """缓存推荐股票数据"""
    recommender = StockRecommender()
    return recommender.get_recommended_stocks_cn(num_stocks=num_stocks)

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
                st.write("**MACD:**", f"{stock['indicators']['macd']:.2f}")
                st.caption(stock['signals']['macd'])
            with cols[1]:
                st.write("**RSI:**", f"{stock['indicators']['rsi']:.2f}")
                st.caption(stock['signals']['rsi'])
            with cols[2]:
                st.write("**KDJ:**", f"K:{stock['indicators']['kdj_k']:.2f} D:{stock['indicators']['kdj_d']:.2f}")
                st.caption(stock['signals']['kdj'])
            with cols[3]:
                boll_lower = stock['indicators'].get('boll_lower', 0)
                boll_upper = stock['indicators'].get('boll_upper', 0)
                st.write("**布林带:**", f"{boll_lower:.2f}-{boll_upper:.2f}")
                st.caption(stock['signals']['boll'])

            st.divider()

@st.cache_data(ttl=CACHE_TTL_SHORT_TERM, show_spinner=False)
def get_cached_short_term_stocks(num_stocks):
    """获取短线推荐股票（基于短期技术指标）"""
    recommender = StockRecommender()
    return recommender.get_short_term_recommendations(num_stocks=num_stocks)

@st.cache_data(ttl=CACHE_TTL_SECTOR, show_spinner=False)
def get_cached_sector_stocks(sector_name, num_stocks):
    """获取板块短线推荐股票"""
    recommender = StockRecommender()
    return recommender.get_sector_short_term_recommendations(sector_name, num_stocks=num_stocks)

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
        if st.button("清除缓存", type="secondary"):
            get_cached_short_term_stocks.clear()
            get_cached_sector_stocks.clear()
            st.session_state.rec_data_loaded = False
            st.success("缓存已清除，已重新加载")

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

def display_watchlist_sidebar():
    """在侧边栏显示自选股列表"""
    watchlist = get_watchlist()

    with st.expander("自选股"):
        if watchlist:
            for item in watchlist:
                col1, col2 = st.columns([4, 1])
                with col1:
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
        else:
            st.caption("暂无自选股")


def display_data_source_selector():
    """显示数据源选择器"""
    with st.expander("数据源设置"):
        current_source = fetcher.get_preferred_source()

        source_options = {
            'auto': '自动选择 (推荐)',
            'akshare': 'AKShare (同花顺/东方财富)',
            'sina': '新浪财经',
            'yfinance': 'Yahoo Finance'
        }

        selected = st.selectbox(
            "优先数据源",
            options=list(source_options.keys()),
            index=list(source_options.keys()).index(current_source),
            format_func=lambda x: source_options[x]
        )

        if selected != current_source:
            fetcher.set_preferred_source(selected)
            st.success(f"已切换到: {source_options[selected]}")
            st.info("请重新获取数据以生效")

def display_health_status():
    """显示数据源健康状态"""
    health = fetcher.check_health()

    with st.expander("数据源健康状态"):
        for source, status in health.items():
            source_names = {
                'akshare': 'AKShare (同花顺)',
                'sina': '新浪财经',
                'yfinance': 'Yahoo Finance'
            }

            if status['healthy']:
                icon = "✅"
                color = "green"
            else:
                icon = "❌"
                color = "red"

            fail_info = f" (失败{status['fail_count']}次)" if status['fail_count'] > 0 else ""
            st.markdown(f"{icon} **{source_names.get(source, source)}**{fail_info}")

def display_data_source_status():
    """显示数据源状态说明"""
    with st.expander("关于数据源"):
        st.markdown("""
        **数据源优先级：**
        1. **AKShare（腾讯财经）** - 主要数据源，数据最全
        2. **新浪财经** - 备选数据源
        3. **Yahoo Finance** - 最终备选

        **数据延迟：**
        - A股：延迟约15分钟（交易所规定）
        - 美股/港股：实时或延迟15分钟
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

        page = st.radio(
            "功能菜单",
            options=["个股分析", "热门板块", "智能推荐", "股票对比"],
            format_func=lambda x: x
        )

        st.markdown("---")

        # 自选股（折叠）
        display_watchlist_sidebar()

        # 数据与状态（合并折叠）
        display_data_source_selector()
        display_health_status()
        display_data_source_status()

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

if __name__ == "__main__":
    main()
