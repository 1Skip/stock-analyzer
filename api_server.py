"""
飞书机器人 API 服务（FastAPI）
接收飞书消息 → 解析命令 → 调用分析 → 返回结果
"""
import json
import logging
import hashlib

logger = logging.getLogger(__name__)

try:
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import JSONResponse
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

app = FastAPI(title="Stock Analyzer API", version="1.0.0") if FASTAPI_AVAILABLE else None


# ============================================================
# 命令处理
# ============================================================

def _get_watchlist_text():
    """生成自选股信号摘要文本"""
    import os
    watchlist_file = os.path.join(os.path.dirname(__file__), 'watchlist.json')
    if not os.path.exists(watchlist_file):
        return "暂无自选股"

    try:
        with open(watchlist_file, 'r', encoding='utf-8') as f:
            watchlist = json.load(f)
    except Exception:
        return "自选股数据读取失败"

    if not watchlist:
        return "暂无自选股。请在网页版添加自选股。"

    from watchlist import get_watchlist_summary
    summaries = get_watchlist_summary(watchlist)

    lines = [f"📊 自选股行情 ({len(summaries)}只)\n"]
    for item in summaries:
        symbol = item['symbol']
        name = item.get('name', symbol)
        market = item.get('market', 'CN')
        market_label = {'CN': 'A股', 'HK': '港股', 'US': '美股'}.get(market, market)

        if item.get('error'):
            lines.append(f"  {symbol} {name} [{market_label}] - ⚠ {item['error']}")
            continue

        price = item.get('price', '--')
        change = item.get('change_pct', 0) or 0
        arrow = "🔴" if change >= 0 else "🟢"
        signal = item.get('signal_summary', '--')
        hint = item.get('entry_hint', '--')

        lines.append(f"  {symbol} {name} [{market_label}]")
        lines.append(f"    ¥{price:.2f} {arrow} {change:+.2f}%")
        lines.append(f"    信号: {signal}")
        lines.append(f"    入场: {hint}")

    return "\n".join(lines)


def _get_analysis_text(symbol, market='CN'):
    """生成个股分析摘要文本"""
    from data_fetcher import StockDataFetcher
    from technical_indicators import TechnicalIndicators

    fetcher = StockDataFetcher()
    df = fetcher.get_stock_data(symbol, period='3mo', market=market)

    if df is None or df.empty or len(df) < 10:
        return f"未找到 {symbol} 的数据"

    df = TechnicalIndicators.calculate_all(df)
    signals = TechnicalIndicators.get_signals(df)

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else latest
    price = latest['close']
    change = (latest['close'] - prev['close']) / prev['close'] * 100 if prev['close'] != 0 else 0

    market_label = {'CN': 'A股', 'HK': '港股', 'US': '美股'}.get(market, market)
    arrow = "🔴" if change >= 0 else "🟢"

    lines = [
        f"📈 {symbol} [{market_label}]",
        f"  价格: ¥{price:.2f} {arrow} {change:+.2f}%",
        f"  信号: {signals.get('recommendation', '--')}",
    ]

    # 关键指标
    parts = []
    for key, label in [('macd', 'MACD'), ('rsi', 'RSI'), ('kdj', 'KDJ'), ('boll', '布林')]:
        val = signals.get(key, '--')
        parts.append(f"{label}: {val}")
    lines.append(f"  {' | '.join(parts)}")

    # 入场提示
    from watchlist import get_entry_hint
    ind = {}
    for k in ('boll_upper', 'boll_mid', 'boll_lower'):
        val = latest.get(k)
        ind[k] = float(val) if val is not None else None
    hint = get_entry_hint(price, ind, signals.get('recommendation', '--'))
    lines.append(f"  入场: {hint}")

    return "\n".join(lines)


def _get_hot_text(market='CN'):
    """生成热门股票摘要文本"""
    from stock_recommendation import StockRecommender
    recommender = StockRecommender()

    if market == 'CN':
        stocks = recommender.get_recommended_stocks_cn(num_stocks=10)
    elif market == 'HK':
        stocks = recommender.get_recommended_stocks_hk(num_stocks=10)
    else:
        stocks = recommender.get_recommended_stocks_us(num_stocks=10)

    market_label = {'CN': 'A股', 'HK': '港股', 'US': '美股'}.get(market, market)
    lines = [f"🔥 热门推荐 [{market_label}]\n"]

    for i, s in enumerate(stocks[:10], 1):
        symbol = s['symbol']
        name = s['name']
        score = s.get('score', '--')
        rating = s.get('rating', '--')
        signal_short = {'偏多信号 (强)': '偏多(强)', '偏多信号': '偏多',
                        '偏空信号 (强)': '偏空(强)', '偏空信号': '偏空',
                        '观望': '观望'}.get(rating, rating)
        lines.append(f"  {i}. {symbol} {name} 评分{score} {signal_short}")

    return "\n".join(lines)


def handle_command(text):
    """解析文本命令，返回回复文本"""
    text = text.strip()

    # /watchlist — 自选股
    if text.startswith('/watchlist') or text in ('自选股', '自选', 'watchlist'):
        return _get_watchlist_text()

    # /hot — 热门推荐
    if text.startswith('/hot') or text in ('热门', '推荐', 'hot'):
        # 可选市场后缀: /hot CN
        parts = text.split()
        market = parts[-1].upper() if len(parts) > 1 and parts[-1].upper() in ('CN', 'HK', 'US') else 'CN'
        return _get_hot_text(market)

    # /analysis <symbol> — 个股分析
    if text.startswith('/analysis') or text.startswith('/分析'):
        parts = text.split()
        symbol = parts[1] if len(parts) > 1 else None
        if not symbol:
            return "请提供股票代码，例如: /analysis 000001"
        # 可选市场
        market = parts[2].upper() if len(parts) > 2 and parts[2].upper() in ('CN', 'HK', 'US') else 'CN'
        return _get_analysis_text(symbol, market)

    # 纯ASCII数字/字母 → 当作股票代码（排除中文等非ASCII字符）
    if text.isascii() and text.isalnum() and len(text) <= 8:
        return _get_analysis_text(text, 'CN')

    return """支持以下命令:
- /watchlist — 查看自选股信号
- /analysis <代码> [市场] — 个股分析
- /hot [市场] — 热门推荐
- 直接输入股票代码 — 快速分析"""


# ============================================================
# API 路由
# ============================================================

if FASTAPI_AVAILABLE:

    @app.get("/")
    def root():
        return {"service": "Stock Analyzer API", "version": "1.0.0"}

    @app.get("/api/watchlist")
    def api_watchlist():
        """获取自选股摘要 (JSON)"""
        import os
        watchlist_file = os.path.join(os.path.dirname(__file__), 'watchlist.json')
        if not os.path.exists(watchlist_file):
            return {"watchlist": [], "message": "暂无自选股"}

        try:
            with open(watchlist_file, 'r', encoding='utf-8') as f:
                watchlist = json.load(f)
        except Exception:
            return {"watchlist": [], "message": "读取失败"}

        if not watchlist:
            return {"watchlist": [], "message": "暂无自选股"}

        from watchlist import get_watchlist_summary
        summaries = get_watchlist_summary(watchlist)
        return {"watchlist": summaries, "count": len(summaries)}

    @app.get("/api/analysis")
    def api_analysis(symbol: str, market: str = "CN"):
        """获取个股分析 (JSON)"""
        try:
            text = _get_analysis_text(symbol, market.upper())
            return {"symbol": symbol, "market": market, "analysis": text}
        except Exception as e:
            return {"symbol": symbol, "error": str(e)[:100]}

    @app.post("/webhook/feishu")
    async def feishu_webhook(request: Request):
        """飞书机器人事件回调"""
        from config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_VERIFY_TOKEN

        body = await request.json()
        logger.debug(f"飞书回调: {json.dumps(body, ensure_ascii=False)[:500]}")

        # 1. URL 验证（challenge）
        challenge = body.get("challenge")
        if challenge:
            token = body.get("token", "")
            if FEISHU_VERIFY_TOKEN and token != FEISHU_VERIFY_TOKEN:
                raise HTTPException(status_code=403, detail="token mismatch")
            return JSONResponse({"challenge": challenge})

        # 2. 消息事件
        event = body.get("event", {})
        msg_type = event.get("message", {}).get("message_type", "")

        if msg_type == "text":
            content = event.get("message", {}).get("content", "{}")
            try:
                content_json = json.loads(content)
                text = content_json.get("text", "")
            except json.JSONDecodeError:
                text = content

            reply = handle_command(text)
            return JSONResponse({"code": 0, "msg": "ok", "data": {"reply": reply}})

        return JSONResponse({"code": 0, "msg": "ignored"})

    @app.get("/health")
    def health_check():
        return {"status": "ok"}


# ============================================================
# 启动入口
# ============================================================

def start():
    """启动 API 服务"""
    if not FASTAPI_AVAILABLE:
        print("FastAPI 未安装。请运行: pip install fastapi uvicorn")
        return

    from config import API_SERVER_PORT
    import uvicorn

    logger.info(f"Stock Analyzer API 启动 — 端口 {API_SERVER_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=API_SERVER_PORT, log_level="info")


if __name__ == "__main__":
    start()
