"""
定时调度模块
基于 schedule 库的每日定时器，支持优雅退出
"""
import signal
import sys
import time
import logging
from datetime import datetime

import schedule

from config import (
    SCHEDULE_TIME, SCHEDULE_RUN_IMMEDIATELY, NOTIFY_ENABLED, NOTIFY_CHANNELS,
)
from notification import send_push, build_analysis_report

logger = logging.getLogger(__name__)


def run_scheduled_analysis():
    """执行一次定时分析：获取推荐股票 → 分析 → 推送通知"""
    logger.info(f"定时分析开始 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        from data_fetcher import StockDataFetcher
        from technical_indicators import TechnicalIndicators
        from stock_recommendation import StockRecommender

        fetcher = StockDataFetcher()
        recommender = StockRecommender()

        reports = []
        for market, market_name in [("CN", "A股"), ("HK", "港股"), ("US", "美股")]:
            try:
                if market == "CN":
                    stocks = recommender.get_recommended_stocks_cn(num_stocks=5)
                elif market == "HK":
                    stocks = recommender.get_recommended_stocks_hk(num_stocks=5)
                else:
                    stocks = recommender.get_recommended_stocks_us(num_stocks=5)
            except Exception:
                logger.warning(f"{market_name} 推荐列表获取失败，跳过")
                continue

            for s in stocks[:5]:
                try:
                    symbol = s["symbol"]
                    name = s["name"]
                    price = s["latest_price"]
                    change_pct = s.get("change_pct", 0)

                    signals = s.get("signals", {})
                    if not signals:
                        data = fetcher.get_stock_data(symbol, period="3mo", market=market)
                        if data is not None and not data.empty:
                            data = TechnicalIndicators.calculate_all(data)
                            signals = TechnicalIndicators.get_signals(data)

                    title, body = build_analysis_report(
                        symbol, name, price, change_pct, signals
                    )
                    reports.append((title, body))
                except Exception as e:
                    logger.warning(f"{s.get('symbol', '?')} 分析失败: {e}")

        if not reports:
            logger.warning("无有效分析结果，跳过推送")
            return

        summary_title = f"📊 每日选股报告 — {datetime.now().strftime('%m-%d')}"
        summary_body = ""
        for title, body in reports:
            summary_body += f"**{title}**\n{body}\n\n---\n\n"

        if NOTIFY_ENABLED:
            results = send_push(summary_title, summary_body.strip())
            success = [ch for ch, ok in results.items() if ok]
            if success:
                logger.info(f"推送成功: {', '.join(success)}")
            else:
                logger.warning("所有渠道推送失败")
        else:
            logger.info("通知未开启，分析结果仅记录日志")

        logger.info(f"定时分析完成 — {len(reports)} 条")

    except Exception as e:
        logger.error(f"定时分析失败: {e}", exc_info=True)


def start_scheduler():
    """启动定时调度循环，处理 SIGINT/SIGTERM 优雅退出"""
    logger.info(f"定时调度已启动 — 每日 {SCHEDULE_TIME} 执行")

    if SCHEDULE_RUN_IMMEDIATELY:
        logger.info("立即执行首次分析...")
        run_scheduled_analysis()

    schedule.every().day.at(SCHEDULE_TIME).do(run_scheduled_analysis)

    def _shutdown(signum, frame):
        logger.info("收到退出信号，调度器关闭")
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    while True:
        schedule.run_pending()
        time.sleep(30)
