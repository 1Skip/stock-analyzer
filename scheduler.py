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
    SECTOR_PUSH_ENABLED, DAILY_REPORT_ENABLED, DAILY_REPORT_PUSH_ENABLED,
    DAILY_REPORT_INCLUDE_RECOMMENDATIONS, DAILY_REPORT_DIR,
    SECTOR_PUSH_SHORT_TOP_N, SECTOR_PUSH_LONG_TOP_N,
)
from notification import send_push, build_analysis_report, build_sector_report
from reports.exporter import save_markdown_report

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


def _generate_daily_report():
    """生成每日 Markdown 报告，失败时返回 None。"""
    try:
        from reports.daily_report_service import DailyReportService
        service = DailyReportService()
        report_date = datetime.now().strftime("%Y-%m-%d")
        content = service.generate_markdown(
            report_date=report_date,
            include_recommendations=DAILY_REPORT_INCLUDE_RECOMMENDATIONS,
        )
        paths = save_markdown_report(content, report_date, output_dir=DAILY_REPORT_DIR)
        logger.info(f"每日报告已生成: {paths['dated']}")
        return content, paths
    except Exception as e:
        logger.warning(f"每日报告生成失败，跳过日报推送: {e}", exc_info=True)
        return None


def run_scheduled_analysis():
    """执行定时分析：自选股摘要 → 四板块推荐 → 每日报告。"""
    logger.info(f"定时分析开始 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        from stock_recommendation import StockRecommender

        recommender = StockRecommender()
        reports = []

        # 优先分析自选股
        watchlist = _load_watchlist_from_file()

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

                title, body = build_analysis_report(
                    symbol, name, price, change_pct,
                    {'recommendation': item['signal_summary'],
                     'entry_hint': item.get('entry_hint', '')}
                )
                reports.append((title, body))

        # 固定四板块推荐：每个板块短线 2 只 + 长线 1 只（可通过环境变量覆盖）
        if SECTOR_PUSH_ENABLED:
            try:
                sector_data = recommender.get_all_sector_recommendations(
                    short_top_n=SECTOR_PUSH_SHORT_TOP_N,
                    long_top_n=SECTOR_PUSH_LONG_TOP_N,
                )
                if sector_data:
                    sector_title, sector_body = build_sector_report(sector_data)
                    reports.append((sector_title, sector_body))
                    logger.info("板块推荐已生成")
            except Exception as e:
                logger.warning(f"板块推荐分析失败，跳过: {e}")

        if not reports and not DAILY_REPORT_ENABLED:
            logger.warning("无有效分析结果，跳过推送")
            return

        if reports:
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
        else:
            logger.warning("无有效选股摘要，继续处理每日报告")

        daily_report = _generate_daily_report() if DAILY_REPORT_ENABLED else None
        if daily_report and NOTIFY_ENABLED and DAILY_REPORT_PUSH_ENABLED:
            report_body, report_paths = daily_report
            report_title = f"📄 每日完整分析报告 — {datetime.now().strftime('%m-%d')}"
            report_body = f"{report_body}\n\n---\n\n报告文件：`{report_paths['dated']}`"
            results = send_push(report_title, report_body.strip())
            success = [ch for ch, ok in results.items() if ok]
            if success:
                logger.info(f"每日报告推送成功: {', '.join(success)}")
            else:
                logger.warning("每日报告所有渠道推送失败")
        elif daily_report:
            logger.info("每日报告已生成，未开启日报推送")

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
