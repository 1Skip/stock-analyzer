"""Recommendation service shared by UI, reports, and push workflows."""
from __future__ import annotations

import concurrent.futures
from datetime import datetime
from typing import Any, Callable

from config import CACHE_TTL_RECOMMENDATION_RESULTS
from data.cache import JsonFileCache
from data.services.quote_service import QuoteDataService
from stock_recommendation import StockRecommender


ProgressCallback = Callable[[str, int, dict[str, Any] | None], None]


class RecommendationService:
    """Run stock recommendation strategies and persist their latest results."""

    def __init__(
        self,
        recommender: StockRecommender | None = None,
        quote_service: QuoteDataService | None = None,
        result_cache: JsonFileCache | None = None,
    ):
        self.recommender = recommender or StockRecommender()
        self.quote_service = quote_service or QuoteDataService()
        self.result_cache = result_cache or JsonFileCache(
            "recommendation_results",
            CACHE_TTL_RECOMMENDATION_RESULTS,
        )

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

    def refresh_strategy_kline_cache(self, *args, **kwargs) -> dict[str, Any]:
        return self.recommender.refresh_strategy_kline_cache(*args, **kwargs)

    def run_all_sector_recommendations(
        self,
        short_top_n: int | None = None,
        long_top_n: int | None = None,
    ) -> dict[str, Any]:
        """Keep the existing sector push semantics on the shared service."""
        return self.recommender.get_all_sector_recommendations(
            short_top_n=short_top_n,
            long_top_n=long_top_n,
        )

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
                if quote:
                    item["latest_price"] = quote["price"]
                    item["change_pct"] = quote["change_pct"]
        except Exception:
            return

    @staticmethod
    def _cache_key(strategy: str, sector: str, num_stocks: int) -> str:
        return f"CN:{strategy}:{sector}:{int(num_stocks or 0)}"
