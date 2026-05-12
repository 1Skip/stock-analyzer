"""每日分析报告服务。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from config import INDEX_WATCHLIST
from data.services.info_service import StockInfoService
from data.services.quote_service import QuoteDataService
from reports.exporter import save_markdown_report
from stock_recommendation import StockRecommender


class DailyReportService:
    """组装并导出每日股票分析报告。"""

    def __init__(
        self,
        quote_service: QuoteDataService | None = None,
        info_service: StockInfoService | None = None,
        recommender: StockRecommender | None = None,
    ):
        self.quote_service = quote_service or QuoteDataService()
        self.info_service = info_service or StockInfoService()
        self.recommender = recommender or StockRecommender()

    def build_report_data(self, report_date: str | None = None, include_recommendations: bool = True) -> dict[str, Any]:
        report_date = report_date or datetime.now().strftime("%Y-%m-%d")
        watchlist_items = self._load_watchlist()
        watchlist_summary = self._get_watchlist_summary(watchlist_items) if watchlist_items else []
        focus_symbols = self._collect_focus_symbols(watchlist_items)

        return {
            "date": report_date,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "market_indices": self._get_market_indices(),
            "watchlist": watchlist_summary,
            "recommendations": self._get_recommendations() if include_recommendations else [],
            "extended_info": self._get_extended_info(focus_symbols),
        }

    def generate_markdown(self, report_date: str | None = None, include_recommendations: bool = True) -> str:
        data = self.build_report_data(report_date=report_date, include_recommendations=include_recommendations)
        return self.render_markdown(data)

    def save_markdown(self, report_date: str | None = None, output_dir: str = "reports/history", include_recommendations: bool = True) -> dict[str, str]:
        report_date = report_date or datetime.now().strftime("%Y-%m-%d")
        content = self.generate_markdown(report_date=report_date, include_recommendations=include_recommendations)
        return save_markdown_report(content, report_date, output_dir=output_dir)

    def _get_market_indices(self) -> list[dict[str, Any]]:
        results = []
        for code, name in INDEX_WATCHLIST:
            quote = self.quote_service.get_index_realtime(code)
            if quote:
                results.append({
                    "symbol": code,
                    "name": quote.get("name") or name,
                    "price": quote.get("price"),
                    "change_pct": quote.get("change_pct"),
                })
        return results

    def _load_watchlist(self) -> list[dict[str, Any]]:
        try:
            from scheduler import _load_watchlist_from_file
            return _load_watchlist_from_file()
        except Exception:
            return []

    def _get_watchlist_summary(self, watchlist_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        try:
            from watchlist import get_watchlist_summary
            return get_watchlist_summary(watchlist_items)
        except Exception:
            return []

    def _get_recommendations(self) -> list[dict[str, Any]]:
        try:
            return self.recommender.get_short_term_recommendations(num_stocks=5) or []
        except Exception:
            return []

    def _collect_focus_symbols(self, watchlist_items: list[dict[str, Any]]) -> list[dict[str, str]]:
        focus = []
        seen = set()
        for item in watchlist_items[:5]:
            symbol = item.get("symbol")
            market = item.get("market", "CN")
            if symbol and market == "CN" and symbol not in seen:
                focus.append({"symbol": symbol, "name": item.get("name", symbol), "market": market})
                seen.add(symbol)
        return focus

    def _get_extended_info(self, focus_symbols: list[dict[str, str]]) -> list[dict[str, Any]]:
        results = []
        for item in focus_symbols:
            info = self.info_service.get_stock_extended_info(item["symbol"], item.get("market", "CN"))
            if info:
                results.append({
                    "symbol": item["symbol"],
                    "name": item.get("name", item["symbol"]),
                    "info": info,
                })
        return results

    def render_markdown(self, data: dict[str, Any]) -> str:
        lines = [
            f"# 每日股票分析报告 — {data['date']}",
            "",
            f"> 生成时间：{data['generated_at']}",
            "",
            "## 大盘温度",
        ]
        indices = data.get("market_indices") or []
        if indices:
            for item in indices:
                lines.append(
                    f"- {item['name']} `{item['symbol']}`：{self._fmt_number(item.get('price'))} "
                    f"({self._fmt_pct(item.get('change_pct'))})"
                )
        else:
            lines.append("- 暂无大盘指数数据")

        lines.extend(["", "## 自选股摘要"])
        watchlist = data.get("watchlist") or []
        if watchlist:
            for item in watchlist:
                if item.get("error"):
                    lines.append(f"- `{item['symbol']}` {item.get('name', '')}：⚠ {item['error']}")
                    continue
                lines.append(
                    f"- `{item['symbol']}` {item.get('name', '')}：{self._fmt_number(item.get('price'))} "
                    f"({self._fmt_pct(item.get('change_pct'))})；"
                    f"信号：{item.get('signal_summary', '--')}；入场：{item.get('entry_hint', '--')}"
                )
        else:
            lines.append("- 暂无自选股")

        lines.extend(["", "## 今日推荐"])
        recommendations = data.get("recommendations") or []
        if recommendations:
            for index, item in enumerate(recommendations, 1):
                lines.append(
                    f"{index}. `{item.get('symbol')}` {item.get('name', '')}：评分 {item.get('score', '--')}，"
                    f"建议 {item.get('rating', '--')}，现价 {self._fmt_number(item.get('latest_price'))}"
                )
        else:
            lines.append("- 暂无推荐结果")

        lines.extend(["", "## 财务 / 资金 / 新闻摘要"])
        extended_items = data.get("extended_info") or []
        if extended_items:
            for item in extended_items:
                info = item.get("info") or {}
                financial = info.get("financial") or {}
                fund_flow = info.get("fund_flow") or {}
                news = info.get("news") or []
                lines.append(f"### `{item['symbol']}` {item.get('name', '')}")
                metrics = financial.get("metrics") or {}
                if metrics:
                    lines.append(
                        f"- 财务期：{financial.get('period', '--')}；"
                        f"营收 {self._fmt_money(metrics.get('营业总收入'))}；"
                        f"归母净利 {self._fmt_money(metrics.get('归母净利润'))}"
                    )
                if fund_flow:
                    lines.append(
                        f"- 资金流：{fund_flow.get('date', '--')} 主力净流入 "
                        f"{self._fmt_money(fund_flow.get('main_net_inflow'))}，"
                        f"近5日 {self._fmt_money(fund_flow.get('five_day_main_net_inflow'))}"
                    )
                if news:
                    for news_item in news[:3]:
                        title = news_item.get("title", "")
                        url = news_item.get("url", "")
                        if url:
                            lines.append(f"- 新闻：[{title}]({url})")
                        else:
                            lines.append(f"- 新闻：{title}")
                if not metrics and not fund_flow and not news:
                    lines.append("- 暂无扩展信息")
        else:
            lines.append("- 暂无扩展信息")

        lines.extend([
            "",
            "## 风险提示",
            "- 本报告仅基于公开数据和技术指标生成，不构成投资建议。",
            "- 数据源可能存在延迟、缺失或临时不可用，请以交易所和券商数据为准。",
            "",
        ])
        return "\n".join(lines)

    @staticmethod
    def _fmt_number(value) -> str:
        if value is None:
            return "--"
        try:
            return f"{float(value):.2f}"
        except Exception:
            return str(value)

    @staticmethod
    def _fmt_pct(value) -> str:
        if value is None:
            return "--"
        try:
            return f"{float(value):+.2f}%"
        except Exception:
            return str(value)

    @staticmethod
    def _fmt_money(value) -> str:
        if value is None:
            return "--"
        try:
            value = float(value)
            if abs(value) >= 1e8:
                return f"{value / 1e8:.2f}亿"
            if abs(value) >= 1e4:
                return f"{value / 1e4:.2f}万"
            return f"{value:.2f}"
        except Exception:
            return str(value)
