"""
股票分析系统集中配置
所有硬编码参数统一管理，支持环境变量覆盖
"""
import os

# ============================================================
# 技术指标参数
# ============================================================
MACD_FAST = int(os.getenv("MACD_FAST", "12"))
MACD_SLOW = int(os.getenv("MACD_SLOW", "26"))
MACD_SIGNAL = int(os.getenv("MACD_SIGNAL", "9"))

RSI_PERIODS = [6, 12, 24]  # RSI 三周期
RSI_OVERBOUGHT = 70        # 超买阈值
RSI_OVERSOLD = 30          # 超卖阈值

KDJ_N = int(os.getenv("KDJ_N", "9"))
KDJ_M1 = int(os.getenv("KDJ_M1", "3"))
KDJ_M2 = int(os.getenv("KDJ_M2", "3"))
KDJ_OVERBOUGHT = 80        # K值超买
KDJ_OVERSOLD = 20          # K值超卖

BOLL_PERIOD = int(os.getenv("BOLL_PERIOD", "20"))
BOLL_STD_DEV = float(os.getenv("BOLL_STD_DEV", "2"))

MA_PERIODS = [5, 10, 20, 60]

# ============================================================
# 数据获取配置
# ============================================================
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY = float(os.getenv("RETRY_DELAY", "1"))

HEALTH_FAIL_THRESHOLD = 3   # 连续失败N次标记为不健康
HEALTH_RECOVERY_MINUTES = 5  # 不健康数据源N分钟后尝试恢复
HEALTH_SKIP_PROBABILITY = 0.5  # fail_count>5时随机跳过概率

OFFLINE_CACHE_MAX_ENTRIES = 20     # 离线缓存最大股票数
OFFLINE_CACHE_MAX_AGE_HOURS = 24   # 离线缓存有效期

SPOT_CACHE_TTL_SECONDS = 60  # 全市场快照缓存时间

# ============================================================
# Streamlit 缓存 TTL（秒）
# ============================================================
CACHE_TTL_REALTIME = 10       # 实时行情
CACHE_TTL_STOCK_DATA = 30     # 历史K线数据
CACHE_TTL_STOCK_INFO = 300    # 股票基本信息
CACHE_TTL_HOT_STOCKS = 180    # 热门股票排行
CACHE_TTL_INDICATORS = 600    # 技术指标计算
CACHE_TTL_RECOMMENDED = 600   # 推荐股票
CACHE_TTL_SHORT_TERM = 600    # 短线推荐
CACHE_TTL_SECTOR = 600        # 板块推荐

# ============================================================
# 配色方案
# ============================================================
# A股传统配色（红涨绿跌），WCAG AA 达标（对比度 ≥4.5:1）
COLOR_RED_UP = {
    "increasing": "#cc0000",   # 涨（红），对比度 ~5.5:1
    "decreasing": "#008844",   # 跌（绿），对比度 ~4.6:1
    "volume_up": "#cc0000",
    "volume_down": "#008844",
    "macd_hist_up": "#cc0000",
    "macd_hist_down": "#008844",
    "label": "A股传统（红涨绿跌）",
}

# 国际惯例配色（绿涨红跌）
COLOR_GREEN_UP = {
    "increasing": "#008844",   # 涨（绿）
    "decreasing": "#cc0000",   # 跌（红）
    "volume_up": "#008844",
    "volume_down": "#cc0000",
    "macd_hist_up": "#008844",
    "macd_hist_down": "#cc0000",
    "label": "国际惯例（绿涨红跌）",
}

# 色盲友好配色（蓝涨橙跌）
COLOR_COLORBLIND = {
    "increasing": "#0066cc",   # 涨（蓝）
    "decreasing": "#e67300",   # 跌（橙）
    "volume_up": "#0066cc",
    "volume_down": "#e67300",
    "macd_hist_up": "#0066cc",
    "macd_hist_down": "#e67300",
    "label": "色盲友好（蓝涨橙跌）",
}

COLOR_SCHEMES = {
    "red_up": COLOR_RED_UP,
    "green_up": COLOR_GREEN_UP,
    "colorblind": COLOR_COLORBLIND,
}

# 各市场默认配色
DEFAULT_COLOR_SCHEME = {
    "CN": "red_up",
    "HK": "green_up",
    "US": "green_up",
}

# ============================================================
# 评分权重
# ============================================================
SCORING_WEIGHTS_MID_LONG = {
    "macd_golden_cross": 15,
    "macd_bullish": 5,
    "macd_death_cross": -15,
    "macd_bearish": -5,
    "rsi_oversold": 15,
    "rsi_low": 10,
    "rsi_overbought": -15,
    "rsi_high": -5,
    "kdj_strong_golden": 20,
    "kdj_golden": 15,
    "kdj_oversold": 10,
    "kdj_strong_death": -20,
    "kdj_death": -15,
    "kdj_overbought": -10,
    "boll_rebound": 15,
    "boll_bullish": 10,
    "boll_pullback": -10,
    "boll_bearish": -5,
    "ma_golden": 20,
    "ma_bullish": 10,
    "ma_bearish": -10,
}

SCORING_WEIGHTS_SHORT_TERM = {
    "macd_golden_cross": 25,
    "macd_bullish": 10,
    "macd_death_cross": -25,
    "macd_bearish": -10,
    "rsi_strong_oversold": 25,
    "rsi_oversold": 20,
    "rsi_low": 10,
    "rsi_overbought": -15,
    "rsi_high": -10,
    "kdj_strong_golden": 30,
    "kdj_golden": 25,
    "kdj_oversold": 20,
    "kdj_strong_death": -30,
    "kdj_death": -25,
    "kdj_overbought": -20,
    "boll_rebound": 20,
    "boll_bullish": 10,
    "boll_pullback": -15,
    "boll_bearish": -10,
    "ma_golden": 30,
    "ma_bullish": 15,
    "ma_bearish": -15,
    "volatility_bonus": 5,
}

# 综合建议信号阈值
SIGNAL_BUY_THRESHOLD = 3    # 偏多信号计数 ≥ N → 偏多信号（强）
SIGNAL_SELL_THRESHOLD = 3   # 偏空信号计数 ≥ N → 偏空信号（强）
SIGNAL_WEAK_THRESHOLD = 2   # 偏多/偏空计数 ≥ N → 偏多/偏空

# 评级区间
RATING_THRESHOLDS = {
    "偏多信号（强）": 80,
    "偏多信号": 65,
    "观望": 50,
    "偏空信号": 35,
    "偏空信号（强）": 0,
}

# ============================================================
# AI 分析配置
# ============================================================
AI_ENABLED = os.getenv("AI_ENABLED", "true").lower() == "true"
AI_MODEL = os.getenv("AI_MODEL", "gemini/gemini-2.5-flash")
AI_API_KEY = os.getenv("AI_API_KEY", None)
AI_BASE_URL = os.getenv("AI_BASE_URL", None)
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.2"))
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "1024"))
AI_CACHE_TTL_SECONDS = int(os.getenv("AI_CACHE_TTL", "300"))

# ============================================================
# 数据源配置
# ============================================================
DEFAULT_DATA_SOURCE = os.getenv("STOCK_DATA_SOURCE", "auto")
DATA_SOURCE_PRIORITY = ["akshare", "sina", "yfinance"]
