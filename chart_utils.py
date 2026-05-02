"""
共享图表工具模块
提供配色解析、成交量/MACD着色、MA配置等图表绘制通用逻辑
供 chart_plotter.py (Matplotlib) 和 app.py (Plotly) 共用
"""
from config import COLOR_SCHEMES, DEFAULT_COLOR_SCHEME

# 移动平均线配置：周期 -> 颜色映射
MA_CONFIG = {
    5:  {"period": 5,  "color": "orange", "label": "MA5"},
    10: {"period": 10, "color": "cyan",   "label": "MA10"},
    20: {"period": 20, "color": "blue",   "label": "MA20"},
    60: {"period": 60, "color": "purple", "label": "MA60"},
}


def resolve_color_scheme(scheme_name=None, market="CN"):
    """解析配色方案，返回完整配色字典"""
    if not scheme_name:
        scheme_name = DEFAULT_COLOR_SCHEME.get(market, "red_up")
    return COLOR_SCHEMES.get(scheme_name, COLOR_SCHEMES["red_up"])


def get_volume_colors(df, up_color, down_color):
    """返回每根成交量柱的颜色列表：涨用up_color，跌用down_color"""
    close_arr = df["close"].values
    open_arr = df["open"].values
    return [up_color if close_arr[i] >= open_arr[i] else down_color
            for i in range(len(df))]


def get_macd_hist_colors(hist_data, up_color, down_color):
    """返回MACD柱状图的颜色列表：>=0用up_color，<0用down_color"""
    return [up_color if v >= 0 else down_color for v in hist_data]
