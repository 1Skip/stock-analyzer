"""
股票分析系统 - Web版本
Streamlit 入口：页面配置 + CSS + 路由
"""
import streamlit as st

# 页面配置（必须在最前面）
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
        --color-primary: #0071e3;
        --color-rise: #ff3b30;
        --color-fall: #34c759;
        --color-warning: #ff9500;
        --color-flat: #8e8e93;
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
        background: rgba(128, 128, 128, 0.03);
        border-radius: 12px;
        padding: 1.25rem;
        margin: 0.6rem 0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        transition: background 0.2s ease;
    }
    .stock-card:hover {
        background: rgba(128, 128, 128, 0.06);
    }

    /* ===== 自选股条目 ===== */
    .watchlist-item {
        background: rgba(128, 128, 128, 0.03);
        border-radius: var(--space-8);
        padding: var(--space-8);
        margin: var(--space-4) 0;
        box-shadow: 0 1px 2px rgba(0,0,0,0.03);
        transition: background 0.2s ease;
    }
    .watchlist-item:hover {
        background: rgba(128, 128, 128, 0.06);
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
        background-color: var(--color-primary);
        color: #fff;
    }
    .stButton button[data-kind="secondary"] {
        background-color: rgba(128, 128, 128, 0.08);
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
        background: rgba(128, 128, 128, 0.03);
        border-radius: var(--space-12);
        padding: 0.75rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
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

# ============================================================
# 模块导入
# ============================================================
from config import MARKET_INDEX_ENABLED
from ui.analyze_page import analyze_stock_page
from ui.hot_stocks_page import hot_stocks_page
from ui.recommend_page import recommended_stocks_page
from ui.compare_page import compare_stocks_page
from ui.sidebar import (
    display_market_temperature,
    display_watchlist_sidebar,
    display_watchlist_mini_panel,
    display_data_source_selector,
)

# ============================================================
# Re-export — 测试兼容（test_app_plotly.py 用 from app import xxx）
# ============================================================
from ui.charts import (  # noqa: F401
    plot_candlestick_chart, plot_rsi_chart, plot_kdj_chart,
    plot_boll_chart, plot_intraday_chart, _indicator_layout,
)
from ui.ai_analysis_ui import _detect_provider, AI_MODEL_OPTIONS  # noqa: F401
from ui.analyze_page import display_signals, _classify_signal, _validate_symbol  # noqa: F401


def main():
    """主函数"""
    with st.sidebar:
        st.title("股票分析系统")
        st.markdown("---")

        _nav_emoji = {"个股分析": "📈", "热门板块": "🔥", "智能推荐": "💡", "股票对比": "📊", "回测验证": "⏮"}
        page = st.radio(
            "功能菜单",
            options=["个股分析", "热门板块", "智能推荐", "股票对比", "回测验证"],
            format_func=lambda x: f"{_nav_emoji.get(x, '')} {x}"
        )

        if MARKET_INDEX_ENABLED:
            display_market_temperature()

        summaries = display_watchlist_sidebar()

        display_watchlist_mini_panel(summaries)

        display_data_source_selector()

        st.caption("风险提示：本系统仅供参考，不构成投资建议")

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
