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

from ui.styles import CUSTOM_CSS

# 自定义CSS样式 — Apple × Tesla 设计体系
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

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
from ui.analyze_page import display_signals, _validate_symbol  # noqa: F401


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
