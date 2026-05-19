"""Recommendation service shared by UI, reports, and push workflows."""
from __future__ import annotations

import concurrent.futures
from datetime import datetime, timedelta
from typing import Any, Callable
import time
import requests

from config import (
    CACHE_TTL_RECOMMENDATION_RESULTS,
    RECOMMEND_RANKER_ENABLED,
    RECOMMEND_RANKER_SORT,
    T1_PLAN_PREHEAT_EXTENDED_INFO_DEEP,
    T1_PLAN_PREHEAT_EXTENDED_INFO_MAX_SYMBOLS,
    T1_PLAN_PREHEAT_EXTENDED_INFO_TIMEOUT_SECONDS,
)
from data.cache import JsonFileCache
from data.services.fundamental_service import FundamentalDataService
from data.services.quote_service import QuoteDataService
from indicator_context import (
    DISPLAY_INDICATOR_PERIOD,
    build_indicator_snapshot,
    prepare_indicator_frame,
)
from quality_monitor import (
    attach_recommendation_explanations,
    evaluate_plan_outcomes,
    list_plan_history,
    save_plan_history,
    summarize_recommendation_quality,
    summarize_history_outcomes,
)
from recommend_ranker import enrich_recommendations_with_alpha
from stock_recommendation import StockRecommender
from trade_plan import enrich_recommendations_with_trade_plan


ProgressCallback = Callable[[str, int, dict[str, Any] | None], None]


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
        if number != number:
            return None
        return number
    except (TypeError, ValueError):
        return None


def _valid_quote_for_display(quote: dict[str, Any] | None) -> bool:
    if not isinstance(quote, dict):
        return False
    price = _safe_float(quote.get("price"))
    if price is None or price <= 0:
        return False
    change_pct = _safe_float(quote.get("change_pct"))
    if change_pct is not None and change_pct <= -99:
        return False
    prev_close = _safe_float(quote.get("prev_close"))
    if prev_close is not None and prev_close <= 0:
        return False
    return True


def _fetch_eastmoney_realtime_quotes(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch A-share realtime quotes from Eastmoney via AKShare."""
    symbols = [str(symbol or "").strip() for symbol in symbols if symbol]
    if not symbols:
        return {}
    try:
        import akshare as ak  # type: ignore

        spot_df = ak.stock_zh_a_spot_em()
    except Exception:
        return {}
    if spot_df is None or getattr(spot_df, "empty", True):
        return {}

    wanted = set(symbols)
    result: dict[str, dict[str, Any]] = {}
    for _, row in spot_df.iterrows():
        symbol = str(row.get("代码") or "").strip()
        if symbol not in wanted:
            continue
        result[symbol] = {
            "symbol": symbol,
            "name": row.get("名称") or symbol,
            "price": _safe_float(row.get("最新价")),
            "change_pct": _safe_float(row.get("涨跌幅")),
            "open": _safe_float(row.get("今开")),
            "prev_close": _safe_float(row.get("昨收")),
            "high": _safe_float(row.get("最高")),
            "low": _safe_float(row.get("最低")),
            "volume": _safe_float(row.get("成交量")),
            "turnover_rate": _safe_float(row.get("换手率")),
            "market_cap": _safe_float(row.get("总市值")),
            "source": "东方财富实时行情",
        }
    return result


def _fetch_tencent_realtime_quotes(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch A-share realtime quotes from Tencent's lightweight quote endpoint."""
    symbols = [str(symbol or "").strip() for symbol in symbols if symbol]
    if not symbols:
        return {}

    def tencent_code(symbol: str) -> str:
        if symbol.startswith("6"):
            return f"sh{symbol}"
        if symbol.startswith(("4", "8")):
            return f"bj{symbol}"
        return f"sz{symbol}"

    result: dict[str, dict[str, Any]] = {}
    try:
        code_to_symbol = {tencent_code(symbol): symbol for symbol in symbols}
        response = requests.get(
            "https://qt.gtimg.cn/q=" + ",".join(code_to_symbol.keys()),
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://stockapp.finance.qq.com/"},
            timeout=5,
        )
        if response.status_code != 200:
            return {}
        for line in response.text.splitlines():
            raw = line.split('"', 2)[1] if '"' in line else ""
            parts = raw.split("~")
            if len(parts) < 46:
                continue
            code = parts[2] if len(parts) > 2 else ""
            symbol = code[-6:] if code else ""
            if symbol not in symbols:
                continue
            price = _safe_float(parts[3])
            prev_close = _safe_float(parts[4])
            change_pct = _safe_float(parts[32])
            if change_pct is None and price is not None and prev_close:
                change_pct = (price / prev_close - 1) * 100
            result[symbol] = {
                "symbol": symbol,
                "name": parts[1] or symbol,
                "price": price,
                "change_pct": change_pct,
                "open": _safe_float(parts[5]),
                "prev_close": prev_close,
                "high": _safe_float(parts[33]),
                "low": _safe_float(parts[34]),
                "volume": _safe_float(parts[6]),
                "turnover_rate": _safe_float(parts[38]),
                "market_cap": (_safe_float(parts[45]) or 0) * 1e8 if _safe_float(parts[45]) else None,
                "source": "腾讯行情",
            }
    except Exception:
        return {}
    return result


class RecommendationService:
    """Run stock recommendation strategies and persist their latest results."""

    def __init__(
        self,
        recommender: StockRecommender | None = None,
        quote_service: QuoteDataService | None = None,
        fundamental_service: FundamentalDataService | None = None,
        result_cache: JsonFileCache | None = None,
    ):
        self.recommender = recommender or StockRecommender()
        self.quote_service = quote_service or QuoteDataService()
        self.fundamental_service = fundamental_service or FundamentalDataService()
        self.result_cache = result_cache or JsonFileCache(
            "recommendation_results",
            CACHE_TTL_RECOMMENDATION_RESULTS,
        )
        self.plan_cache = JsonFileCache("recommendation_t1_plans", 86400 * 14)
        self.plan_history_cache = JsonFileCache("recommendation_t1_plan_history", 86400 * 120)

    def run(
        self,
        strategy: str,
        sector: str,
        num_stocks: int,
        progress_callback: ProgressCallback | None = None,
        *,
        use_cache: bool = False,
    ) -> dict[str, Any]:
        """Run a recommendation strategy.

        Strategy conditions live in ``StockRecommender``; this service only
        routes requests, refreshes final quotes, and stores the result.
        """
        strategy = str(strategy or "短线")
        sector = str(sector or "全部")
        num_stocks = int(num_stocks or 5)
        cache_key = self._cache_key(strategy, sector, num_stocks)
        if use_cache:
            cached = self.result_cache.get(cache_key)
            if isinstance(cached, dict):
                return cached

        result = self._run_uncached(strategy, sector, num_stocks, progress_callback)
        result["generated_at"] = datetime.now().isoformat(timespec="seconds")
        result["strategy"] = strategy
        result["sector"] = sector
        result["num_stocks"] = num_stocks
        self.result_cache.set(cache_key, result)
        return result

    def latest(self, strategy: str, sector: str, num_stocks: int) -> dict[str, Any] | None:
        cached = self.result_cache.get(self._cache_key(strategy, sector, num_stocks))
        return cached if isinstance(cached, dict) else None

    def run_t1_plan(
        self,
        strategy: str,
        sector: str,
        num_stocks: int,
        progress_callback: ProgressCallback | None = None,
        *,
        trigger: str = "manual",
        preheat_kline: bool = False,
        preheat_extended_info: bool = False,
    ) -> dict[str, Any]:
        """Generate and persist a T+1 plan without changing strategy rules."""
        started = time.perf_counter()
        preheat_status: dict[str, Any] = {
            "trigger": trigger,
            "kline_cache": "not_requested",
            "extended_info_cache": "not_requested",
        }
        if preheat_kline:
            preheat_status["kline_cache"] = self._preheat_kline_cache()

        result = self.run(
            strategy,
            sector,
            num_stocks,
            progress_callback=progress_callback,
            use_cache=False,
        )
        if preheat_extended_info:
            preheat_status["extended_info_cache"] = self._preheat_extended_info_cache(result.get("recommended"))

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        plan = self._wrap_t1_plan(result, strategy, sector, num_stocks)
        plan["generation_metrics"] = {
            "trigger": trigger,
            "elapsed_ms": elapsed_ms,
            "elapsed_seconds": round(elapsed_ms / 1000, 2),
            "selection_source": "StockRecommender existing strategy",
            "realtime_used_for_selection": False,
            "scan_scope_changed": False,
        }
        plan["data_status"].update({
            "source": "fresh_scan",
            "preheat": preheat_status,
        })
        self.plan_cache.set(self._plan_cache_key(strategy, sector, num_stocks), plan)
        plan["history_key"] = save_plan_history(self.plan_history_cache, plan)
        return plan

    def latest_t1_plan(self, strategy: str, sector: str, num_stocks: int) -> dict[str, Any] | None:
        started = time.perf_counter()
        cached = self.plan_cache.get(self._plan_cache_key(strategy, sector, num_stocks))
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if not isinstance(cached, dict):
            return None
        cached = dict(cached)
        data_status = dict(cached.get("data_status") or {})
        data_status["source"] = "t1_plan_cache"
        data_status["cache_read_metrics"] = {
            "elapsed_ms": elapsed_ms,
            "elapsed_seconds": round(elapsed_ms / 1000, 3),
            "realtime_used_for_selection": False,
            "scan_scope_changed": False,
        }
        cached["data_status"] = data_status
        return cached

    def check_entry_plan(self, plan: dict[str, Any] | None) -> dict[str, Any]:
        """Check whether planned stocks are still executable; never re-pick stocks."""
        if not isinstance(plan, dict):
            return {
                "status": "no_plan",
                "message": "暂无 T+1 推荐计划，无法执行入场检查。",
                "items": [],
            }
        recommended = plan.get("recommended") or []
        symbols = [str(item.get("symbol") or "").strip() for item in recommended if item.get("symbol")]
        if not symbols:
            return {
                "status": "empty_plan",
                "message": "T+1 推荐计划为空，无法执行入场检查。",
                "items": [],
            }
        quotes, source = self._fetch_entry_realtime_quotes(symbols)
        if not isinstance(quotes, dict) or not quotes:
            return {
                "status": "realtime_unavailable",
                "message": "实时行情不可用，仅展示昨晚 T+1 推荐计划；本次不生成入场建议，请以券商行情为准。",
                "checked_at": datetime.now().isoformat(timespec="seconds"),
                "source": source or "全部实时源失败",
                "items": [],
            }

        items = []
        for stock in recommended:
            symbol = str(stock.get("symbol") or "").strip()
            quote = quotes.get(symbol) or {}
            items.append(self._build_entry_check_item(stock, quote))
        return {
            "status": "ok",
            "message": "入场检查完成：检查结果只用于执行判断，不改变昨晚推荐列表。",
            "checked_at": datetime.now().isoformat(timespec="seconds"),
            "source": source,
            "items": items,
        }

    def evaluate_t1_plan_outcomes(self, plan: dict[str, Any] | None) -> dict[str, Any]:
        """Read-only T+1 outcome review; never changes future recommendations."""
        return evaluate_plan_outcomes(plan, quote_service=self.quote_service)

    def list_t1_plan_history(
        self,
        *,
        strategy: str | None = None,
        sector: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return saved T+1 plans. Read-only and separate from latest-plan cache."""
        return list_plan_history(self.plan_history_cache, strategy=strategy, sector=sector, limit=limit)

    def evaluate_t1_plan_history(
        self,
        *,
        strategy: str | None = None,
        sector: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Evaluate stored plans without feeding results back into the strategy."""
        rows = self.list_t1_plan_history(strategy=strategy, sector=sector, limit=limit)
        reviews = []
        for row in rows:
            plan = row.get("plan") or {}
            reviews.append({
                "plan": plan,
                "outcome": self.evaluate_t1_plan_outcomes(plan),
            })
        return {
            "history": rows,
            "reviews": reviews,
            "summary": summarize_history_outcomes(reviews),
        }

    def refresh_strategy_kline_cache(self, *args, **kwargs) -> dict[str, Any]:
        return self.recommender.refresh_strategy_kline_cache(*args, **kwargs)

    def run_all_sector_recommendations(
        self,
        short_top_n: int | None = None,
        long_top_n: int | None = None,
    ) -> dict[str, Any]:
        """Keep the existing sector push semantics on the shared service."""
        sector_data = self.recommender.get_all_sector_recommendations(
            short_top_n=short_top_n,
            long_top_n=long_top_n,
        )
        return self._attach_sector_explanations(sector_data)

    def _run_uncached(
        self,
        strategy: str,
        sector: str,
        num_stocks: int,
        progress_callback: ProgressCallback | None,
    ) -> dict[str, Any]:
        diagnostics: dict[str, Any] = {}
        if strategy == "短线":
            if sector == "全部":
                recommended = self.recommender.get_short_term_recommendations(num_stocks)
                title = "短线推荐"
            else:
                recommended = self.recommender.get_sector_short_term_recommendations(sector, num_stocks)
                title = f"{sector} 短线推荐"
        elif strategy == "长线":
            if sector == "全部":
                recommended = self.recommender.get_long_term_recommendations(num_stocks)
                title = "长线推荐"
            else:
                recommended = self.recommender.get_sector_long_term_recommendations(sector, num_stocks)
                title = f"{sector} 长线推荐"
        elif strategy == "激进突破型":
            if sector == "全部":
                recommended = self.recommender.get_aggressive_breakout_recommendations(
                    num_stocks,
                    progress_callback=progress_callback,
                )
                title = "激进突破型"
            else:
                recommended = self.recommender.get_sector_aggressive_breakout_recommendations(
                    sector,
                    num_stocks,
                    progress_callback=progress_callback,
                )
                title = f"{sector} 激进突破型"
            diagnostics = self.recommender.last_aggressive_diagnostics
        elif strategy == "多因子稳健型":
            if sector == "全部":
                recommended = self.recommender.get_multi_factor_recommendations(
                    num_stocks,
                    progress_callback=progress_callback,
                )
                title = "多因子稳健型"
            else:
                recommended = self.recommender.get_sector_multi_factor_recommendations(
                    sector,
                    num_stocks,
                    progress_callback=progress_callback,
                )
                title = f"{sector} 多因子稳健型"
            diagnostics = self.recommender.last_multi_factor_diagnostics
        else:
            recommended = self.recommender.get_long_term_recommendations(num_stocks)
            title = "长线推荐"

        self._refresh_final_quotes(recommended)
        if RECOMMEND_RANKER_ENABLED:
            recommended = enrich_recommendations_with_alpha(
                recommended,
                strategy=strategy,
                sector=sector,
                sort=RECOMMEND_RANKER_SORT,
            )
            diagnostics = dict(diagnostics or {})
            diagnostics["alpha_ranker"] = {
                "enabled": True,
                "sorted": RECOMMEND_RANKER_SORT,
                "version": "alpha_v1",
            }
        recommended = attach_recommendation_explanations(
            recommended,
            strategy=strategy,
            sector=sector,
        )
        enrich_recommendations_with_trade_plan(
            recommended,
            strategy=strategy,
            sector=sector,
        )
        diagnostics = dict(diagnostics or {})
        diagnostics["quality"] = summarize_recommendation_quality(recommended)
        return {
            "recommended": recommended,
            "title": title,
            "diagnostics": diagnostics,
        }

    def _refresh_final_quotes(self, recommended: list[dict[str, Any]] | None) -> None:
        if not recommended:
            return
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self.quote_service.get_batch_realtime_quotes,
                    [s["symbol"] for s in recommended if s.get("symbol")],
                    "CN",
                )
                quotes = future.result(timeout=3)
            for item in recommended:
                quote = quotes.get(item.get("symbol")) if isinstance(quotes, dict) else None
                if _valid_quote_for_display(quote):
                    item["latest_price"] = quote["price"]
                    item["change_pct"] = quote["change_pct"]
                    item["_display_quote"] = quote
        except Exception:
            quotes = {}
        self._refresh_display_profiles(recommended)
        self._refresh_display_indicators(recommended)

    def _refresh_display_profiles(self, recommended: list[dict[str, Any]] | None) -> None:
        """Fill display profile fields for recommendation cards without changing strategy results."""
        if not recommended:
            return
        for item in recommended:
            symbol = str(item.get("symbol") or "").strip()
            if not symbol:
                continue
            current = item.get("profile") if isinstance(item.get("profile"), dict) else {}
            needs_profile = any(
                current.get(key) in (None, "", {})
                for key in ("industry", "market_cap", "pe_ttm", "pb", "turnover_rate")
            )
            if not current or needs_profile:
                try:
                    fetched = self.fundamental_service.get_stock_profile(symbol, "CN")
                except Exception:
                    fetched = None
                if isinstance(fetched, dict) and fetched:
                    merged = dict(current)
                    for key, value in fetched.items():
                        if merged.get(key) in (None, "", {}) and value not in (None, "", {}):
                            merged[key] = value
                    current = merged
            if current:
                item["profile"] = current

    def _refresh_display_indicators(self, recommended: list[dict[str, Any]] | None) -> None:
        """Recompute displayed indicators with the same context as the stock analysis page."""
        if not recommended:
            return
        for item in recommended:
            symbol = str(item.get("symbol") or "").strip()
            if not symbol:
                continue
            quote = item.pop("_display_quote", None)
            try:
                data = self.quote_service.get_stock_data(
                    symbol,
                    period=DISPLAY_INDICATOR_PERIOD,
                    market="CN",
                    adjust="qfq",
                )
                indicator_frame = prepare_indicator_frame(data)
                snapshot = build_indicator_snapshot(indicator_frame)
            except Exception:
                snapshot = {}
            if snapshot:
                item["indicators"] = snapshot
                item["display_indicator_context"] = {
                    "period": DISPLAY_INDICATOR_PERIOD,
                    "adjust": "qfq",
                    "formula": "TechnicalIndicators on forward-adjusted daily K-line",
                    "realtime_merged": False,
                }

    @staticmethod
    def _attach_sector_explanations(sector_data: dict[str, Any] | None) -> dict[str, Any]:
        """Attach explanation blocks to sector push results without changing order."""
        if not isinstance(sector_data, dict):
            return {}
        enriched: dict[str, Any] = {}
        for sector, strategies in sector_data.items():
            enriched[sector] = {}
            for strategy, stocks in (strategies or {}).items():
                strategy_stocks = attach_recommendation_explanations(
                    stocks or [],
                    strategy=strategy,
                    sector=sector,
                )
                enriched[sector][strategy] = enrich_recommendations_with_trade_plan(
                    strategy_stocks,
                    strategy=strategy,
                    sector=sector,
                )
        return enriched

    def _preheat_kline_cache(self) -> dict[str, Any]:
        try:
            result = self.refresh_strategy_kline_cache()
            return {
                "status": "ok",
                "total": result.get("total", 0),
                "refreshed": result.get("refreshed", 0),
                "failed": result.get("failed", 0),
            }
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}

    def _preheat_extended_info_cache(self, recommended: list[dict[str, Any]] | None) -> dict[str, Any]:
        stocks = recommended or []
        if not stocks:
            return {
                "status": "skipped",
                "reason": "empty_recommendation",
                "total": 0,
                "attempted": 0,
                "refreshed": 0,
                "failed": 0,
                "skipped": 0,
                "deep_layers": T1_PLAN_PREHEAT_EXTENDED_INFO_DEEP,
            }
        symbols = [
            str((stock or {}).get("symbol") or "").strip()
            for stock in stocks
            if str((stock or {}).get("symbol") or "").strip()
        ]
        invalid = len(stocks) - len(symbols)
        max_symbols = max(0, int(T1_PLAN_PREHEAT_EXTENDED_INFO_MAX_SYMBOLS or 0))
        timeout_seconds = max(0.0, float(T1_PLAN_PREHEAT_EXTENDED_INFO_TIMEOUT_SECONDS or 0))
        if max_symbols <= 0:
            return {
                "status": "skipped",
                "reason": "max_symbols_zero",
                "total": len(stocks),
                "attempted": 0,
                "refreshed": 0,
                "failed": 0,
                "skipped": len(stocks),
                "max_symbols": max_symbols,
                "timeout_seconds": timeout_seconds,
                "deep_layers": T1_PLAN_PREHEAT_EXTENDED_INFO_DEEP,
            }
        selected_symbols = symbols[:max_symbols]
        limit_skipped = max(0, len(symbols) - len(selected_symbols))
        started = time.perf_counter()
        try:
            from data.services.info_service import StockInfoService
            info_service = StockInfoService()
            attempted = 0
            refreshed = 0
            failed = 0
            timed_out = False
            for symbol in selected_symbols:
                if timeout_seconds > 0 and (time.perf_counter() - started) >= timeout_seconds:
                    timed_out = True
                    break
                attempted += 1
                try:
                    payload = info_service.get_stock_extended_info(
                        symbol,
                        "CN",
                        include_deep_layers=T1_PLAN_PREHEAT_EXTENDED_INFO_DEEP,
                    )
                    if isinstance(payload, dict):
                        refreshed += 1
                    else:
                        failed += 1
                except Exception:
                    failed += 1
            timeout_skipped = max(0, len(selected_symbols) - attempted) if timed_out else 0
            skipped = invalid + limit_skipped + timeout_skipped
            if timed_out:
                status = "timeout"
            elif failed and refreshed:
                status = "partial"
            elif failed:
                status = "failed"
            elif skipped:
                status = "partial"
            else:
                status = "ok"
            return {
                "status": status,
                "total": len(stocks),
                "attempted": attempted,
                "refreshed": refreshed,
                "failed": failed,
                "skipped": skipped,
                "max_symbols": max_symbols,
                "timeout_seconds": timeout_seconds,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "deep_layers": T1_PLAN_PREHEAT_EXTENDED_INFO_DEEP,
            }
        except Exception as exc:
            return {
                "status": "failed",
                "error": str(exc),
                "total": len(stocks),
                "attempted": 0,
                "refreshed": 0,
                "failed": len(stocks),
                "skipped": 0,
                "max_symbols": max_symbols,
                "timeout_seconds": timeout_seconds,
                "deep_layers": T1_PLAN_PREHEAT_EXTENDED_INFO_DEEP,
            }

    def _fetch_entry_realtime_quotes(self, symbols: list[str]) -> tuple[dict[str, dict[str, Any]], str]:
        quotes = _fetch_eastmoney_realtime_quotes(symbols)
        if quotes:
            return quotes, "东方财富实时行情"
        try:
            quotes = self.quote_service.get_batch_realtime_quotes(symbols, "CN")
        except Exception:
            quotes = {}
        if quotes:
            for item in quotes.values():
                if isinstance(item, dict):
                    item.setdefault("source", "新浪财经")
            return quotes, "新浪财经"
        quotes = _fetch_tencent_realtime_quotes(symbols)
        if quotes:
            return quotes, "腾讯行情"
        return {}, "全部实时源失败"

    def _wrap_t1_plan(self, result: dict[str, Any], strategy: str, sector: str, num_stocks: int) -> dict[str, Any]:
        now = datetime.now()
        generated_trade_date = now.date().isoformat()
        plan_for_trade_date = self._next_trade_date(now).date().isoformat()
        plan = dict(result)
        plan.update({
            "mode": "T+1_PLAN",
            "generated_at": now.isoformat(timespec="seconds"),
            "generated_trade_date": generated_trade_date,
            "plan_for_trade_date": plan_for_trade_date,
            "strategy": str(strategy or "短线"),
            "sector": str(sector or "全部"),
            "num_stocks": int(num_stocks or 5),
            "data_status": {
                "kline_cache": "ready",
                "extended_info_cache": "ready",
                "realtime_check": "not_checked",
            },
        })
        return plan

    @staticmethod
    def _next_trade_date(now: datetime) -> datetime:
        candidate = now + timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)
        return candidate

    @staticmethod
    def _build_entry_check_item(stock: dict[str, Any], quote: dict[str, Any]) -> dict[str, Any]:
        symbol = stock.get("symbol")
        name = stock.get("name") or symbol
        latest_price = _safe_float(quote.get("price"))
        change_pct = _safe_float(quote.get("change_pct"))
        plan_price = _safe_float(stock.get("latest_price") or stock.get("price"))
        open_price = _safe_float(quote.get("open"))
        prev_close = _safe_float(quote.get("prev_close"))
        high_price = _safe_float(quote.get("high"))
        low_price = _safe_float(quote.get("low"))
        volume = _safe_float(quote.get("volume"))
        indicators = stock.get("indicators") if isinstance(stock.get("indicators"), dict) else {}
        boll_lower = _safe_float(indicators.get("boll_lower"))
        risky_notice = RecommendationService._entry_risk_notice(stock)
        status = "可按计划观察"
        reason = "实时价格未明显偏离昨晚计划。"
        if latest_price is None:
            status = "暂缓入场"
            reason = "实时价格缺失，无法判断当前买点。"
        elif RecommendationService._is_st_or_delisting_name(name):
            status = "暂缓入场"
            reason = "股票名称含 ST/退市风险标识，入场前需先核对风险提示。"
        elif risky_notice:
            status = "暂缓入场"
            reason = f"发现风险公告：{risky_notice}，暂不生成入场建议。"
        elif RecommendationService._looks_suspended_or_no_trade(quote, latest_price, open_price, high_price, low_price, volume):
            status = "暂缓入场"
            reason = "实时行情显示无成交或无有效交易，疑似停牌/未正常交易，暂缓入场。"
        elif open_price is not None and prev_close and prev_close > 0 and (open_price / prev_close - 1) * 100 >= 5:
            gap_pct = (open_price / prev_close - 1) * 100
            status = "等待回落"
            reason = f"今日高开 {gap_pct:.2f}%，超过计划节奏，等待回落再观察。"
        elif change_pct is not None and change_pct >= 5:
            status = "等待回落"
            reason = f"当前涨幅 {change_pct:.2f}%，追高风险较高。"
        elif change_pct is not None and change_pct <= -5:
            status = "暂缓入场"
            reason = f"当前跌幅 {change_pct:.2f}%，走势弱于计划假设。"
        elif boll_lower is not None and latest_price < boll_lower:
            status = "暂缓入场"
            reason = f"当前价格跌破 BOLL 下轨支撑 {boll_lower:.2f}，需等待支撑确认。"
        elif plan_price:
            try:
                drift_pct = (float(latest_price) / float(plan_price) - 1) * 100
                if drift_pct >= 5:
                    status = "等待回落"
                    reason = f"当前价较计划价高 {drift_pct:.2f}%，不建议追高。"
                elif drift_pct <= -5:
                    status = "暂缓入场"
                    reason = f"当前价较计划价低 {abs(drift_pct):.2f}%，需确认支撑。"
            except Exception:
                pass
        return {
            "symbol": symbol,
            "name": name,
            "status": status,
            "reason": reason,
            "plan_price": plan_price,
            "latest_price": latest_price,
            "change_pct": change_pct,
            "quote": quote,
        }

    @staticmethod
    def _is_st_or_delisting_name(name: Any) -> bool:
        text = str(name or "").upper()
        return "ST" in text or "退" in text

    @staticmethod
    def _looks_suspended_or_no_trade(
        quote: dict[str, Any],
        latest_price: float | None,
        open_price: float | None,
        high_price: float | None,
        low_price: float | None,
        volume: float | None,
    ) -> bool:
        if "volume" not in quote or volume is None or volume != 0:
            return False
        if latest_price in (None, 0) or open_price in (None, 0) or high_price in (None, 0) or low_price in (None, 0):
            return True
        return open_price == high_price == low_price == latest_price

    @staticmethod
    def _entry_risk_notice(stock: dict[str, Any]) -> str | None:
        risk_events = stock.get("risk_events") if isinstance(stock.get("risk_events"), dict) else None
        if risk_events is None and isinstance(stock.get("extended_info"), dict):
            risk_events = stock["extended_info"].get("risk_events")
        announcements = (risk_events or {}).get("announcements") if isinstance(risk_events, dict) else []
        risky_keywords = ("减持", "立案", "处罚", "风险", "诉讼", "亏损", "退市", "监管", "问询", "警示")
        for item in announcements or []:
            if isinstance(item, dict):
                text = " ".join(str(item.get(key) or "") for key in ("title", "type", "summary", "content"))
            else:
                text = str(item or "")
            if any(keyword in text for keyword in risky_keywords):
                return text[:80]
        return None

    @staticmethod
    def _cache_key(strategy: str, sector: str, num_stocks: int) -> str:
        return f"CN:{strategy}:{sector}:{int(num_stocks or 0)}"

    @staticmethod
    def _plan_cache_key(strategy: str, sector: str, num_stocks: int) -> str:
        return f"CN:{strategy}:{sector}:{int(num_stocks or 0)}:T1"
