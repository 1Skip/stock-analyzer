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
    SECTOR_PUSH_ENABLED,
)
from notification import send_push, build_analysis_report, build_sector_report

logger = logging.getLogger(__name__)


def _load_watchlist_from_file():
    """从 watchlist.json 读取自选股（不依赖 Streamlit session_state）"""
    import json
    import os
    watchlist_file = os.path.join(os.path.dirname(__file__), 'watchlist.json')
    if os.path.exists(watchlist_file):
        try:
            with open(watchlist_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []


def run_scheduled_analysis():
    """执行一次定时分析：自选股优先 → 推荐股补充 → 推送通知"""
    logger.info(f"定时分析开始 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        from data_fetcher import StockDataFetcher
        from technical_indicators import TechnicalIndicators
        from stock_recommendation import StockRecommender

        fetcher = StockDataFetcher()
        recommender = StockRecommender()
        reports = []

        # 优先分析自选股
        watchlist = _load_watchlist_from_file()
        analyzed_symbols = set()

        if watchlist:
            logger.info(f"自选股模式：{len(watchlist)} 只")
            from watchlist import get_watchlist_summary
            summaries = get_watchlist_summary(watchlist)
            for item in summaries:
                if item.get('error'):
                    logger.warning(f"自选股 {item['symbol']} 分析失败: {item['error']}")
                    continue
                symbol = item['symbol']
                name = item['name']
                price = item['price'] or 0
                change_pct = item.get('change_pct', 0) or 0
                analyzed_symbols.add((symbol, item['market']))

                title, body = build_analysis_report(
                    symbol, name, price, change_pct,
                    {'recommendation': item['signal_summary'],
                     'entry_hint': item.get('entry_hint', '')}
                )
                reports.append((title, body))

        # 推荐股补充（跳过已在自选股中的）
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

            added = 0
            for s in stocks:
                if (s["symbol"], market) in analyzed_symbols:
                    continue
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
                    added += 1
                    if added >= 3:
                        break
                except Exception as e:
                    logger.warning(f"{s.get('symbol', '?')} 分析失败: {e}")

        if not reports and not SECTOR_PUSH_ENABLED:
            logger.warning("无有效分析结果，跳过推送")
            return

        # 板块龙头推荐（短线+长线），默认关闭，失败不影响主推送
        if SECTOR_PUSH_ENABLED:
            try:
                sector_data = recommender.get_all_sector_recommendations()
                if sector_data:
                    sector_title, sector_body = build_sector_report(sector_data)
                    reports.append((sector_title, sector_body))
                    logger.info("板块推荐已生成")
            except Exception as e:
                logger.warning(f"板块推荐分析失败，跳过: {e}")

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

        logger.info(f"定时分析完成 — {len(reports)} 条（含{len(watchlist)}只自选股）")

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
