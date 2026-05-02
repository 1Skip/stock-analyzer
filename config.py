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
CACHE_TTL_STOCK_DATA = 120    # 历史K线数据（2分钟，减少重复请求）
CACHE_TTL_STOCK_INFO = 300    # 股票基本信息
CACHE_TTL_HOT_STOCKS = 180    # 热门股票排行
CACHE_TTL_INDICATORS = 600    # 技术指标计算
CACHE_TTL_RECOMMENDED = 600   # 推荐股票
CACHE_TTL_SHORT_TERM = 600    # 短线推荐
CACHE_TTL_SECTOR = 600        # 板块推荐

# ============================================================
# 配色方案
# ============================================================
# A股传统配色（红涨绿跌）
COLOR_RED_UP = {
    "increasing": "#e53935",   # 涨（红），对比度 ~5.1:1
    "decreasing": "#2e7d32",   # 跌（绿），对比度 ~5.3:1
    "volume_up": "#e53935",
    "volume_down": "#2e7d32",
    "macd_hist_up": "#e53935",
    "macd_hist_down": "#2e7d32",
    "label": "A股传统（红涨绿跌）",
}

# 国际惯例配色（绿涨红跌）
COLOR_GREEN_UP = {
    "increasing": "#2e7d32",   # 涨（绿）
    "decreasing": "#e53935",   # 跌（红）
    "volume_up": "#2e7d32",
    "volume_down": "#e53935",
    "macd_hist_up": "#2e7d32",
    "macd_hist_down": "#e53935",
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
AI_MODEL = os.getenv("AI_MODEL", "deepseek/deepseek-chat")
AI_API_KEY = os.getenv("AI_API_KEY", None)
AI_BASE_URL = os.getenv("AI_BASE_URL", None)
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.2"))
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "1024"))
AI_CACHE_TTL_SECONDS = int(os.getenv("AI_CACHE_TTL", "300"))
AI_MULTI_AGENT = os.getenv("AI_MULTI_AGENT", "false").lower() == "true"  # 多Agent协作分析

# ============================================================
# 数据源配置
# ============================================================
DEFAULT_DATA_SOURCE = os.getenv("STOCK_DATA_SOURCE", "auto")
DATA_SOURCE_PRIORITY = ["akshare", "sina", "yfinance"]

# ============================================================
# 定时调度配置
# ============================================================
SCHEDULE_TIME = os.getenv("SCHEDULE_TIME", "15:30")  # 收盘后30分钟
SCHEDULE_RUN_IMMEDIATELY = os.getenv("SCHEDULE_RUN_IMMEDIATELY", "false").lower() == "true"
SCHEDULE_ENABLED = os.getenv("SCHEDULE_ENABLED", "false").lower() == "true"

# ============================================================
# 通知推送配置
# ============================================================
NOTIFY_CHANNELS = [c.strip() for c in os.getenv("NOTIFY_CHANNELS", "").split(",") if c.strip()]
NOTIFY_ENABLED = len(NOTIFY_CHANNELS) > 0

# 企业微信
WECHAT_WEBHOOK_URL = os.getenv("WECHAT_WEBHOOK_URL", "")

# 飞书
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL", "")

# ============================================================
# 回测配置
# ============================================================
BACKTEST_EVAL_WINDOW = int(os.getenv("BACKTEST_EVAL_WINDOW", "20"))   # 评估窗口（交易日）
BACKTEST_MIN_HISTORY = int(os.getenv("BACKTEST_MIN_HISTORY", "60"))   # 最小历史数据（交易日）
BACKTEST_NEUTRAL_BAND = float(os.getenv("BACKTEST_NEUTRAL_BAND", "2.0"))  # 中性区间（%）
BACKTEST_STOP_LOSS = float(os.getenv("BACKTEST_STOP_LOSS", "-5.0"))   # 止损线（%）
BACKTEST_TAKE_PROFIT = float(os.getenv("BACKTEST_TAKE_PROFIT", "10.0"))  # 止盈线（%）
BACKTEST_RESULTS_DIR = os.getenv("BACKTEST_RESULTS_DIR", "backtest_results")

# ============================================================
# 大盘指数配置
# ============================================================
# 大盘温度功能开关（默认关闭）
MARKET_INDEX_ENABLED = os.getenv("MARKET_INDEX_ENABLED", "true").lower() == "true"
# 监控的A股指数列表（代码: 名称）
INDEX_WATCHLIST = [
    ("000001", "上证指数"),
    ("399001", "深证成指"),
    ("399006", "创业板指"),
]
# 大盘行情缓存TTL（秒）
INDEX_CACHE_TTL = int(os.getenv("INDEX_CACHE_TTL", "10"))
