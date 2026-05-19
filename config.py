"""
股票分析系统集中配置
所有硬编码参数统一管理，支持环境变量覆盖
"""
import os
import sys
from pathlib import Path


def _load_local_env() -> None:
    """加载项目根目录 .env，方便本机启动时读取私密配置。"""
    if "pytest" in sys.modules:
        return
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_local_env()

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
RUNTIME_CACHE_DIR = os.getenv("RUNTIME_CACHE_DIR", os.path.join(os.path.dirname(__file__), ".cache"))

SPOT_CACHE_TTL_SECONDS = 60  # 全市场快照缓存时间

# ============================================================
# Streamlit 缓存 TTL（秒）
# ============================================================
CACHE_TTL_REALTIME = 30       # 实时行情（30秒，减少全市场快照下载）
CACHE_TTL_STOCK_DATA = 600   # 普通页面历史K线数据（10分钟，减少重复请求）
CACHE_TTL_STOCK_INFO = 300    # 股票基本信息
CACHE_TTL_FUNDAMENTALS = 86400  # 市值/行业/上市日期等基础资料（按天缓存）
CACHE_TTL_STOCK_EXTENDED_INFO = 3600  # 资金流/财务/新闻/研报/公告扩展信息（30-60分钟）
CACHE_TTL_STOCK_FINANCIAL = int(os.getenv("CACHE_TTL_STOCK_FINANCIAL", "86400"))  # 财务摘要（按天缓存）
CACHE_TTL_STOCK_RESEARCH = int(os.getenv("CACHE_TTL_STOCK_RESEARCH", "86400"))    # 研报/分红/板块归因（按天缓存）
CACHE_TTL_STOCK_RISK_EVENTS = int(os.getenv("CACHE_TTL_STOCK_RISK_EVENTS", "86400"))  # 公告/风险事件（按天缓存）
CACHE_TTL_STOCK_FUND_FLOW = int(os.getenv("CACHE_TTL_STOCK_FUND_FLOW", "3600"))   # 资金流（30-60分钟）
CACHE_TTL_STRATEGY_KLINE = 86400  # 智能推荐历史K线（按交易日缓存）
CACHE_TTL_RECOMMENDATION_RESULTS = int(os.getenv("CACHE_TTL_RECOMMENDATION_RESULTS", "3600"))  # 智能推荐结果缓存
CACHE_TTL_INTRADAY = 60       # 分时图数据（1分钟）
CACHE_TTL_HOT_STOCKS = 180    # 热门股票排行
CACHE_TTL_INDICATORS = 600    # 技术指标计算
CACHE_TTL_WATCHLIST_SUMMARY = 300  # 自选股摘要（5分钟）

# 板块推送配置
SECTOR_PUSH_ENABLED = os.getenv("SECTOR_PUSH_ENABLED", "true").lower() == "true"
SECTOR_PUSH_TOP_N = int(os.getenv("SECTOR_PUSH_TOP_N", "3"))
SECTOR_PUSH_SHORT_TOP_N = int(os.getenv("SECTOR_PUSH_SHORT_TOP_N", "2"))
SECTOR_PUSH_LONG_TOP_N = int(os.getenv("SECTOR_PUSH_LONG_TOP_N", "1"))

# 每日报告配置
DAILY_REPORT_ENABLED = os.getenv("DAILY_REPORT_ENABLED", "true").lower() == "true"
DAILY_REPORT_PUSH_ENABLED = os.getenv("DAILY_REPORT_PUSH_ENABLED", "true").lower() == "true"
DAILY_REPORT_INCLUDE_RECOMMENDATIONS = os.getenv("DAILY_REPORT_INCLUDE_RECOMMENDATIONS", "false").lower() == "true"
DAILY_REPORT_DIR = os.getenv("DAILY_REPORT_DIR", "reports/history")

# 智能推荐 Alpha 二次排序。默认先展示分数和理由，不改变原策略排序。
RECOMMEND_RANKER_ENABLED = os.getenv("RECOMMEND_RANKER_ENABLED", "true").lower() == "true"
RECOMMEND_RANKER_SORT = os.getenv("RECOMMEND_RANKER_SORT", "false").lower() == "true"

# ============================================================
# 配色方案
# ============================================================
# A股传统配色（红涨绿跌）— Apple 系统色
COLOR_RED_UP = {
    "increasing": "#ff3b30",   # 涨（红），Apple SF Red
    "decreasing": "#34c759",   # 跌（绿），Apple SF Green
    "volume_up": "#ff3b30",
    "volume_down": "#34c759",
    "macd_hist_up": "#ff3b30",
    "macd_hist_down": "#34c759",
    "label": "A股传统（红涨绿跌）",
}

# 国际惯例配色（绿涨红跌）— Apple 系统色
COLOR_GREEN_UP = {
    "increasing": "#34c759",   # 涨（绿），Apple SF Green
    "decreasing": "#ff3b30",   # 跌（红），Apple SF Red
    "volume_up": "#34c759",
    "volume_down": "#ff3b30",
    "macd_hist_up": "#34c759",
    "macd_hist_down": "#ff3b30",
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

# 长线评分权重（相比短线/标准评分：降低RSI/KDJ权重，提高MA60/MACD趋势权重）
LONG_TERM_WEIGHTS = {
    "macd_golden_cross": 20,
    "macd_bullish": 12,
    "macd_death_cross": -15,
    "rsi_oversold_strong": 10,
    "rsi_oversold": 8,
    "rsi_oversold_mild": 5,
    "rsi_overbought_strong": -8,
    "rsi_overbought": -5,
    "kdj_golden_cross_strong": 15,
    "kdj_golden_cross": 10,
    "kdj_oversold": 8,
    "boll_bounce": 12,
    "boll_bullish": 8,
    "boll_pullback": -10,
    "boll_bearish": -5,
    "ma20_above_ma60": 15,
    "ma20_cross_above_ma60": 15,
    "ma20_below_ma60": -15,
    "ma20_uptrend": 8,
    "ma20_downtrend": -8,
}

# ============================================================
# AI 分析配置
# ============================================================
AI_ENABLED = os.getenv("AI_ENABLED", "true").lower() == "true"
AI_MODEL = os.getenv("AI_MODEL", "deepseek/deepseek-chat")
AI_API_KEY = None if "pytest" in sys.modules else os.getenv("AI_API_KEY", None)
AI_BASE_URL = os.getenv("AI_BASE_URL", None)
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.2"))
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "1024"))
AI_CACHE_TTL_SECONDS = int(os.getenv("AI_CACHE_TTL", "300"))
AI_MULTI_AGENT = os.getenv("AI_MULTI_AGENT", "false").lower() == "true"  # 多Agent协作分析
AI_DEBATE_ENABLED = os.getenv("AI_DEBATE_ENABLED", "false").lower() == "true"  # A股多空辩论/风控委员会
AI_DEBATE_MAX_SYMBOLS = int(os.getenv("AI_DEBATE_MAX_SYMBOLS", "3"))

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

# T+1 推荐计划自动预生成配置。只提前运行既有推荐策略，不改变选股条件。
T1_PLAN_AUTO_ENABLED = os.getenv("T1_PLAN_AUTO_ENABLED", "true").lower() == "true"
T1_PLAN_SCHEDULE_TIME = os.getenv("T1_PLAN_SCHEDULE_TIME", "15:45")
_T1_PLAN_STRATEGIES_RAW = os.getenv(
    "T1_PLAN_STRATEGIES",
    os.getenv("T1_PLAN_STRATEGY", "短线,长线,多因子稳健型,激进突破型"),
)
T1_PLAN_STRATEGIES = [item.strip() for item in _T1_PLAN_STRATEGIES_RAW.split(",") if item.strip()]
T1_PLAN_STRATEGY = T1_PLAN_STRATEGIES[0] if T1_PLAN_STRATEGIES else "多因子稳健型"
_T1_PLAN_SECTORS_RAW = os.getenv(
    "T1_PLAN_SECTORS",
    os.getenv("T1_PLAN_SECTOR", "全部,苹果概念,特斯拉概念,电力,算力租赁"),
)
T1_PLAN_SECTORS = [item.strip() for item in _T1_PLAN_SECTORS_RAW.split(",") if item.strip()]
T1_PLAN_SECTOR = T1_PLAN_SECTORS[0] if T1_PLAN_SECTORS else "全部"
T1_PLAN_NUM_STOCKS = int(os.getenv("T1_PLAN_NUM_STOCKS", "5"))
T1_PLAN_PREHEAT_KLINE = os.getenv("T1_PLAN_PREHEAT_KLINE", "true").lower() == "true"
T1_PLAN_PREHEAT_EXTENDED_INFO = os.getenv("T1_PLAN_PREHEAT_EXTENDED_INFO", "true").lower() == "true"
T1_PLAN_PREHEAT_EXTENDED_INFO_MAX_SYMBOLS = int(os.getenv("T1_PLAN_PREHEAT_EXTENDED_INFO_MAX_SYMBOLS", "5"))
T1_PLAN_PREHEAT_EXTENDED_INFO_TIMEOUT_SECONDS = float(os.getenv("T1_PLAN_PREHEAT_EXTENDED_INFO_TIMEOUT_SECONDS", "20"))
T1_PLAN_PREHEAT_EXTENDED_INFO_DEEP = os.getenv("T1_PLAN_PREHEAT_EXTENDED_INFO_DEEP", "false").lower() == "true"
T1_PLAN_STRATEGY_TIMEOUT_SECONDS = float(os.getenv("T1_PLAN_STRATEGY_TIMEOUT_SECONDS", "300"))
T1_PLAN_PUSH_ENABLED = os.getenv("T1_PLAN_PUSH_ENABLED", "true").lower() == "true"

# ============================================================
# 通知推送配置
# ============================================================
NOTIFY_CHANNELS = [c.strip() for c in os.getenv("NOTIFY_CHANNELS", "").split(",") if c.strip()]
NOTIFY_ENABLED = len(NOTIFY_CHANNELS) > 0

# 企业微信
WECHAT_WEBHOOK_URL = os.getenv("WECHAT_WEBHOOK_URL", "")

# 飞书
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL", "")

# 飞书机器人（对话式，控制命令）
FEISHU_BOT_ENABLED = os.getenv("FEISHU_BOT_ENABLED", "false").lower() == "true"
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_VERIFY_TOKEN = os.getenv("FEISHU_VERIFY_TOKEN", "")  # 事件订阅验证 Token

# API 服务
GITHUB_WATCHLIST_SYNC_ENABLED = os.getenv("GITHUB_WATCHLIST_SYNC_ENABLED", "false").lower() == "true"
GITHUB_WATCHLIST_SYNC_REPO = os.getenv("GITHUB_WATCHLIST_SYNC_REPO", os.getenv("GITHUB_REPO", ""))
GITHUB_WATCHLIST_SYNC_SECRET = os.getenv("GITHUB_WATCHLIST_SYNC_SECRET", "WATCHLIST_JSON")
GITHUB_WATCHLIST_SYNC_TIMEOUT = float(os.getenv("GITHUB_WATCHLIST_SYNC_TIMEOUT", "15"))

API_SERVER_PORT = int(os.getenv("API_SERVER_PORT", "8900"))
API_SERVER_HOST = os.getenv("API_SERVER_HOST", "127.0.0.1")  # 默认仅本地访问
API_AUTH_KEY = os.getenv("API_AUTH_KEY", "")  # API 鉴权密钥（为空则跳过验证）
API_CORS_ORIGINS = os.getenv("API_CORS_ORIGINS", "")  # 允许的跨域来源，逗号分隔

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
# 大盘温度功能开关（默认开启）
MARKET_INDEX_ENABLED = os.getenv("MARKET_INDEX_ENABLED", "true").lower() == "true"
# 监控的A股指数列表（代码: 名称）
INDEX_WATCHLIST = [
    ("000001", "上证指数"),
    ("399001", "深证成指"),
    ("000300", "沪深300"),
    ("899050", "北证50"),
]
# 大盘行情缓存TTL（秒）
INDEX_CACHE_TTL = int(os.getenv("INDEX_CACHE_TTL", "10"))
