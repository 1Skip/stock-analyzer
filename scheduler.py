"""
定时调度模块
基于 schedule 库的每日定时器，支持优雅退出
"""
import signal
import sys
import time
import logging
import os
import json
import subprocess
from datetime import datetime
from functools import wraps
from pathlib import Path

import schedule

from config import (
    SCHEDULE_TIME, SCHEDULE_RUN_IMMEDIATELY, NOTIFY_ENABLED,
    DAILY_REPORT_ENABLED, DAILY_REPORT_PUSH_ENABLED,
    DAILY_REPORT_INCLUDE_RECOMMENDATIONS, DAILY_REPORT_DIR,
    T1_PLAN_AUTO_ENABLED, T1_PLAN_SCHEDULE_TIME, T1_PLAN_STRATEGIES,
    T1_PLAN_SECTOR, T1_PLAN_SECTORS, T1_PLAN_NUM_STOCKS, T1_PLAN_PREHEAT_KLINE,
    T1_PLAN_PREHEAT_EXTENDED_INFO, T1_PLAN_STRATEGY_TIMEOUT_SECONDS,
    T1_PLAN_PUSH_ENABLED,
)
from notification import send_push, build_analysis_report, build_t1_plan_report
from reports.exporter import save_markdown_report

logger = logging.getLogger(__name__)

LOCK_DIR = Path(os.getenv("SCHEDULER_LOCK_DIR", ".cache"))
SCHEDULER_INSTANCE_LOCK_PATH = LOCK_DIR / "scheduler.instance.lock"
SCHEDULED_ANALYSIS_LOCK_PATH = LOCK_DIR / "scheduled_analysis.lock"
T1_PREHEAT_LOCK_PATH = LOCK_DIR / "t1_plan_preheat.lock"


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_lock_pid(lock_path: Path) -> int | None:
    try:
        first_line = lock_path.read_text(encoding="utf-8").splitlines()[0]
        return int(first_line.strip())
    except Exception:
        return None


def _acquire_pid_lock(lock_path: Path) -> int | None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            payload = f"{os.getpid()}\n{datetime.now().isoformat(timespec='seconds')}\n"
            os.write(fd, payload.encode("utf-8"))
            return fd
        except FileExistsError:
            pid = _read_lock_pid(lock_path)
            if pid is None or not _process_exists(pid):
                try:
                    lock_path.unlink()
                    continue
                except OSError:
                    return None
            return None


def _release_pid_lock(fd: int | None, lock_path: Path) -> None:
    if fd is not None:
        try:
            os.close(fd)
        except OSError:
            pass
    try:
        if _read_lock_pid(lock_path) == os.getpid():
            lock_path.unlink()
    except OSError:
        pass


def _skip_if_locked(lock_path: Path, label: str):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            fd = _acquire_pid_lock(lock_path)
            if fd is None:
                logger.warning("%s 正在执行，跳过本次重复触发", label)
                return None
            try:
                return func(*args, **kwargs)
            finally:
                _release_pid_lock(fd, lock_path)

        return wrapper

    return decorator


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


@_skip_if_locked(T1_PREHEAT_LOCK_PATH, "T+1 推荐计划预生成")
def run_t1_plan_preheat():
    """自动生成 T+1 推荐计划；只调用既有策略，不改变选股条件。"""
    logger.info(
        "T+1 推荐计划预生成开始：strategies=%s sectors=%s num=%s",
        ",".join(T1_PLAN_STRATEGIES),
        ",".join(T1_PLAN_SECTORS or [T1_PLAN_SECTOR]),
        T1_PLAN_NUM_STOCKS,
    )
    plans = {}
    try:
        from recommendation_service import RecommendationService

        service = RecommendationService()
        for strategy, sector in _iter_t1_plan_targets():
            try:
                plan = _run_t1_plan_strategy_with_timeout(
                    service,
                    strategy,
                    sector,
                    T1_PLAN_NUM_STOCKS,
                )
                plans[f"{strategy}:{sector}"] = plan
                metrics = plan.get("generation_metrics") or {}
                logger.info(
                    "T+1 推荐计划预生成完成：strategy=%s sector=%s，%s 只，耗时 %.2fs",
                    strategy,
                    sector,
                    len(plan.get("recommended") or []),
                    metrics.get("elapsed_seconds", 0),
                )
            except Exception as exc:
                plans[f"{strategy}:{sector}"] = None
                logger.error("T+1 推荐计划预生成失败：strategy=%s sector=%s error=%s", strategy, sector, exc, exc_info=True)
        _push_t1_plan_preheat_results(plans)
        return plans
    except Exception as e:
        logger.error(f"T+1 推荐计划预生成失败: {e}", exc_info=True)
        return None


@_skip_if_locked(SCHEDULED_ANALYSIS_LOCK_PATH, "定时分析")
def run_scheduled_analysis():
    """执行 15:30 定时分析：自选股摘要 → 每日完整报告。"""
    logger.info(f"定时分析开始 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        reports = []

        # 优先分析自选股
        watchlist = _load_watchlist_from_file()

        if watchlist:
            logger.info(f"自选股模式：{len(watchlist)} 只")
            from watchlist import get_watchlist_summary
            from decision_committee import build_watchlist_decision
            from data.services.info_service import StockInfoService

            summaries = get_watchlist_summary(watchlist)
            info_service = StockInfoService()
            for item in summaries:
                if item.get('error'):
                    logger.warning(f"自选股 {item['symbol']} 分析失败: {item['error']}")
                    continue
                symbol = item['symbol']
                name = item['name']
                price = item['price'] or 0
                change_pct = item.get('change_pct', 0) or 0
                extended_info = {}
                try:
                    source = next(
                        (stock for stock in watchlist if stock.get("symbol") == symbol),
                        {},
                    )
                    extended_info = info_service.get_stock_extended_info(
                        symbol,
                        source.get("market", item.get("market", "CN")),
                    ) or {}
                except Exception as exc:
                    logger.info(f"自选股 {symbol} 扩展信息获取失败，推送使用基础交易计划: {exc}")
                decision = build_watchlist_decision(item, extended_info)

                title, body = build_analysis_report(
                    symbol, name, price, change_pct,
                    {'recommendation': item['signal_summary'],
                     'entry_hint': item.get('entry_hint', '')},
                    decision=decision,
                    extended_info=extended_info,
                    indicators=item.get("indicators") or {},
                )
                reports.append((title, body))

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


def _push_t1_plan_preheat_results(plans: dict) -> None:
    if not T1_PLAN_PUSH_ENABLED or not NOTIFY_ENABLED:
        return
    valid_plans = {
        strategy: plan
        for strategy, plan in (plans or {}).items()
        if isinstance(plan, dict)
    }
    if not valid_plans:
        return
    try:
        title, body = build_t1_plan_report(valid_plans)
        results = send_push(title, body)
        success = [channel for channel, ok in results.items() if ok]
        if success:
            logger.info("T+1 plan push succeeded: %s", ", ".join(success))
        else:
            logger.warning("T+1 plan push failed on all channels")
    except Exception as exc:
        logger.warning("T+1 plan push failed: %s", exc, exc_info=True)


def _iter_t1_plan_targets() -> list[tuple[str, str]]:
    sectors = T1_PLAN_SECTORS or [T1_PLAN_SECTOR]
    targets: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for strategy in T1_PLAN_STRATEGIES:
        strategy_text = str(strategy or "").strip()
        if not strategy_text:
            continue
        strategy_sectors = sectors if strategy_text in {"短线", "长线"} else ["全部"]
        for sector in strategy_sectors:
            sector_text = str(sector or "全部").strip() or "全部"
            target = (strategy_text, sector_text)
            if target in seen:
                continue
            seen.add(target)
            targets.append(target)
    return targets


def _run_t1_plan_strategy_with_timeout(service, strategy: str, sector: str, num_stocks: int) -> dict:
    """Run one scheduler T+1 strategy with a process-level timeout."""
    timeout_seconds = float(T1_PLAN_STRATEGY_TIMEOUT_SECONDS or 0)
    if timeout_seconds <= 0:
        return service.run_t1_plan(
            strategy,
            sector,
            num_stocks,
            trigger="scheduler",
            preheat_kline=T1_PLAN_PREHEAT_KLINE,
            preheat_extended_info=T1_PLAN_PREHEAT_EXTENDED_INFO,
        )

    script = """
import json
import sys
from recommendation_service import RecommendationService

strategy = sys.argv[1]
sector = sys.argv[2]
num_stocks = int(sys.argv[3])
preheat_kline = sys.argv[4].lower() == "true"
preheat_extended_info = sys.argv[5].lower() == "true"
plan = RecommendationService().run_t1_plan(
    strategy,
    sector,
    num_stocks,
    trigger="scheduler",
    preheat_kline=preheat_kline,
    preheat_extended_info=preheat_extended_info,
)
print("__T1_PLAN_JSON__" + json.dumps(plan, ensure_ascii=False, default=str))
"""
    started = time.perf_counter()
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            script,
            str(strategy),
            str(sector),
            str(num_stocks),
            str(bool(T1_PLAN_PREHEAT_KLINE)).lower(),
            str(bool(T1_PLAN_PREHEAT_EXTENDED_INFO)).lower(),
        ],
        cwd=str(Path(__file__).resolve().parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.error("T+1 preheat timeout: strategy=%s timeout=%.0fs", strategy, timeout_seconds)
        return _t1_plan_failure(
            strategy,
            sector,
            num_stocks,
            "timeout",
            f"strategy scan exceeded {timeout_seconds:.0f}s",
            elapsed_ms,
        )

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if process.returncode != 0:
        detail = (stderr or stdout or f"exit code {process.returncode}").strip()[-1000:]
        return _t1_plan_failure(strategy, sector, num_stocks, "failed", detail, elapsed_ms)

    for line in reversed((stdout or "").splitlines()):
        if line.startswith("__T1_PLAN_JSON__"):
            return json.loads(line[len("__T1_PLAN_JSON__"):])
    detail = (stdout or stderr or "child process returned no plan json").strip()[-1000:]
    return _t1_plan_failure(strategy, sector, num_stocks, "failed", detail, elapsed_ms)


def _terminate_process_tree(process) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        process.kill()
    try:
        process.wait(timeout=5)
    except Exception:
        pass


def _t1_plan_failure(strategy: str, sector: str, num_stocks: int, status: str, error: str, elapsed_ms: int) -> dict:
    return {
        "mode": "T+1_PLAN",
        "status": status,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "strategy": strategy,
        "sector": sector,
        "num_stocks": num_stocks,
        "recommended": [],
        "generation_metrics": {
            "trigger": "scheduler",
            "elapsed_ms": elapsed_ms,
            "elapsed_seconds": round(elapsed_ms / 1000, 2),
            "selection_source": "StockRecommender existing strategy",
            "realtime_used_for_selection": False,
            "scan_scope_changed": False,
        },
        "data_status": {
            "source": "scheduler_preheat",
            "status": status,
            "error": error,
        },
    }


def start_scheduler():
    """启动定时调度循环，处理 SIGINT/SIGTERM 优雅退出"""
    instance_lock_fd = _acquire_pid_lock(SCHEDULER_INSTANCE_LOCK_PATH)
    if instance_lock_fd is None:
        logger.warning("调度器已经在运行，本次启动已跳过，避免重复生成和重复推送")
        return

    logger.info(f"定时调度已启动 — 每日 {SCHEDULE_TIME} 执行")

    try:
        if SCHEDULE_RUN_IMMEDIATELY:
            logger.info("立即执行首次分析...")
            run_scheduled_analysis()

        schedule.every().day.at(SCHEDULE_TIME).do(run_scheduled_analysis)
        if T1_PLAN_AUTO_ENABLED:
            schedule.every().day.at(T1_PLAN_SCHEDULE_TIME).do(run_t1_plan_preheat)
            logger.info(f"T+1 推荐计划自动预生成已开启：每日 {T1_PLAN_SCHEDULE_TIME} 执行")

        def _shutdown(signum, frame):
            logger.info("收到退出信号，调度器关闭")
            _release_pid_lock(instance_lock_fd, SCHEDULER_INSTANCE_LOCK_PATH)
            sys.exit(0)

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        while True:
            schedule.run_pending()
            time.sleep(30)
    finally:
        _release_pid_lock(instance_lock_fd, SCHEDULER_INSTANCE_LOCK_PATH)
