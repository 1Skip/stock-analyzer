"""每日分析报告服务。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from config import (
    AI_API_KEY,
    AI_BASE_URL,
    AI_DEBATE_ENABLED,
    AI_DEBATE_MAX_SYMBOLS,
    AI_MODEL,
    INDEX_WATCHLIST,
)
from data.services.info_service import StockInfoService
from data.services.quote_service import QuoteDataService
from decision_committee import build_watchlist_decision
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
        extended_info = self._get_extended_info(focus_symbols)
        decision_map = self._build_committee_map(watchlist_summary, extended_info)

        return {
            "date": report_date,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "market_indices": self._get_market_indices(),
            "watchlist": watchlist_summary,
            "recommendations": self._get_recommendations() if include_recommendations else [],
            "extended_info": extended_info,
            "decisions": decision_map,
            "debates": self._get_debate_results(watchlist_summary, extended_info, decision_map),
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
            f"# 每日股票决策仪表盘 — {data['date']}",
            "",
            f"> 生成时间：{data['generated_at']}",
            "",
            "## 核心结论",
        ]
        watchlist = data.get("watchlist") or []
        recommendations = data.get("recommendations") or []
        extended_items = data.get("extended_info") or []
        decision_map = data.get("decisions") or self._build_committee_map(watchlist, extended_items)
        debate_map = data.get("debates") or {}
        top_watch = self._top_watch_item(watchlist)
        if top_watch:
            top_decision = decision_map.get(top_watch.get("symbol")) or {}
            lines.append(
                f"- 自选股重点：`{top_watch.get('symbol')}` {top_watch.get('name', '')}，"
                f"决策 {top_decision.get('action', '--')}，评分 {top_decision.get('score', '--')}，"
                f"仓位 {top_decision.get('position', '--')}，风险 {top_decision.get('risk_level', '--')}，"
                f"置信度 {top_decision.get('confidence', '--')}%"
            )
        elif recommendations:
            item = recommendations[0]
            lines.append(
                f"- 推荐池重点：`{item.get('symbol')}` {item.get('name', '')}，"
                f"评分 {item.get('score', '--')}，建议 {item.get('rating', '--')}"
            )
        else:
            lines.append("- 今日暂无明确高优先级标的，保持观察。")
        lines.append(f"- 风险事件覆盖：{sum(1 for item in extended_items if self._risk_count(item.get('info') or {}) > 0)} 只标的存在公告/龙虎榜/解禁等事件记录。")

        lines.extend([
            "",
            "## 大盘温度",
        ])
        indices = data.get("market_indices") or []
        if indices:
            for item in indices:
                lines.append(
                    f"- {item['name']} `{item['symbol']}`：{self._fmt_number(item.get('price'))} "
                    f"({self._fmt_pct(item.get('change_pct'))})"
                )
        else:
            lines.append("- 暂无大盘指数数据")

        lines.extend(["", "## 自选股决策仪表盘"])
        if watchlist:
            for item in watchlist:
                if item.get("error"):
                    lines.append(f"- `{item['symbol']}` {item.get('name', '')}：⚠ {item['error']}")
                    continue
                decision = decision_map.get(item.get("symbol")) or build_watchlist_decision(item)
                score = decision.get("score", self._decision_score(item))
                lines.append(f"### `{item['symbol']}` {item.get('name', '')}")
                lines.append(
                    f"- **决策仪表盘**：评分 **{score}/100**，"
                    f"行动 **{decision.get('action', '--')}**，仓位 **{decision.get('position', '--')}**，"
                    f"风险 **{decision.get('risk_level', '--')}**，置信度 **{decision.get('confidence', '--')}%**。"
                )
                lines.append(
                    f"- **价格状态**：现价 {self._fmt_number(item.get('price'))} "
                    f"({self._fmt_pct(item.get('change_pct'))})；"
                    f"买卖点：{decision.get('entry_hint') or item.get('entry_hint', '--')}"
                )
                key_levels = decision.get("key_levels") or {}
                if key_levels:
                    lines.append(
                        f"- **关键价位**：支撑 {self._fmt_number(key_levels.get('support'))}，"
                        f"中轨 {self._fmt_number(key_levels.get('mid'))}，"
                        f"压力 {self._fmt_number(key_levels.get('resistance'))}，"
                        f"MA20 {self._fmt_number(key_levels.get('ma20'))}"
                    )
                catalysts = "；".join((decision.get("catalysts") or [])[:3])
                if catalysts:
                    lines.append(f"- **催化因素**：{catalysts}")
                for point in (decision.get("bullish_points") or [])[:2]:
                    lines.append(f"  - 看多依据：{point}")
                for risk in (decision.get("risk_alerts") or [])[:2]:
                    lines.append(f"  - 风险警报：{risk}")
                debate = debate_map.get(item.get("symbol")) or {}
                if debate:
                    lines.extend(self._render_debate_lines(debate))
        else:
            lines.append("- 暂无自选股")

        lines.extend(["", "## 推荐池"])
        if recommendations:
            for index, item in enumerate(recommendations, 1):
                lines.append(
                    f"{index}. `{item.get('symbol')}` {item.get('name', '')}：评分 {item.get('score', '--')}，"
                    f"建议 {item.get('rating', '--')}，现价 {self._fmt_number(item.get('latest_price'))}"
                )
        else:
            lines.append("- 暂无推荐结果")

        lines.extend(["", "## 研报 / 风险 / 板块归因"])
        if extended_items:
            for item in extended_items:
                info = item.get("info") or {}
                financial = info.get("financial") or {}
                fund_flow = info.get("fund_flow") or {}
                news = info.get("news") or []
                research = info.get("research") or {}
                risk_events = info.get("risk_events") or {}
                sector_attribution = info.get("sector_attribution") or {}
                decision = decision_map.get(item.get("symbol")) or {}
                lines.append(f"### `{item['symbol']}` {item.get('name', '')}")
                if decision:
                    lines.append(
                        f"- A股决策委员会：{decision.get('summary', '--')} "
                        f"操作 {decision.get('action', '--')}，仓位 {decision.get('position', '--')}"
                    )
                    for agent in (decision.get("agents") or [])[:5]:
                        lines.append(
                            f"  - {agent.get('name')}：{agent.get('stance')} "
                            f"({agent.get('score_delta'):+})，权重 {agent.get('weight')}，"
                            f"置信度 {agent.get('confidence')}%，{agent.get('summary')}"
                        )
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
                if research.get("eps_consensus"):
                    eps = research["eps_consensus"].get("values") or {}
                    if eps:
                        lines.append(f"- 一致预期 EPS：{self._fmt_key_values(eps)}")
                for report in (research.get("reports") or [])[:2]:
                    label = f"{report.get('date', '')} {report.get('org', '')}".strip()
                    title = report.get("title", "")
                    pdf_url = report.get("pdf_url", "")
                    if pdf_url:
                        lines.append(f"- 研报：{label} [{title}]({pdf_url})")
                    else:
                        lines.append(f"- 研报：{label} {title}".strip())
                industry = sector_attribution.get("industry") or {}
                concepts = sector_attribution.get("concepts") or []
                if industry:
                    lines.append(
                        f"- 行业归因：{industry.get('name')} "
                        f"({self._fmt_pct(industry.get('change_pct'))})；{industry.get('reason', '')}"
                    )
                if concepts:
                    concept_text = "、".join(
                        f"{c.get('name')}({self._fmt_pct(c.get('change_pct'))})" for c in concepts[:5]
                    )
                    lines.append(f"- 概念归因：{concept_text}")
                risk_lines = self._risk_lines(risk_events)
                for risk_line in risk_lines:
                    lines.append(f"- 风险警报：{risk_line}")
                if news:
                    for news_item in news[:3]:
                        title = news_item.get("title", "")
                        url = news_item.get("url", "")
                        if url:
                            lines.append(f"- 新闻：[{title}]({url})")
                        else:
                            lines.append(f"- 新闻：{title}")
                if not metrics and not fund_flow and not news and not research and not risk_lines and not industry and not concepts:
                    lines.append("- 暂无扩展信息")
        else:
            lines.append("- 暂无扩展信息")

        lines.extend(["", "## 操作检查清单"])
        checklist = self._operation_checklist(watchlist, extended_items)
        for item in checklist:
            lines.append(f"- {item}")

        lines.extend([
            "",
            "## 风险提示",
            "- 本报告仅基于公开数据和技术指标生成，不构成投资建议。",
            "- 数据源可能存在延迟、缺失或临时不可用，请以交易所和券商数据为准。",
            "",
        ])
        return "\n".join(lines)

    @staticmethod
    def _top_watch_item(watchlist: list[dict[str, Any]]) -> dict[str, Any] | None:
        valid = [item for item in watchlist if not item.get("error")]
        if not valid:
            return None
        return max(valid, key=lambda item: DailyReportService._decision_score(item))

    def _build_committee_map(
        self,
        watchlist: list[dict[str, Any]],
        extended_items: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        info_map = {
            item.get("symbol"): item.get("info") or {}
            for item in extended_items
            if item.get("symbol")
        }
        decisions = {}
        for item in watchlist:
            symbol = item.get("symbol")
            if not symbol or item.get("error"):
                continue
            decisions[symbol] = build_watchlist_decision(item, info_map.get(symbol, {}))
        return decisions

    def _get_debate_results(
        self,
        watchlist: list[dict[str, Any]],
        extended_items: list[dict[str, Any]],
        decision_map: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        if not AI_DEBATE_ENABLED or not AI_API_KEY:
            return {}
        try:
            from ai_analysis import run_debate_analysis
        except Exception:
            return {}

        info_map = {
            item.get("symbol"): item.get("info") or {}
            for item in extended_items
            if item.get("symbol")
        }
        results = {}
        for item in watchlist[: max(0, AI_DEBATE_MAX_SYMBOLS)]:
            symbol = item.get("symbol")
            decision = decision_map.get(symbol)
            if not symbol or not decision or item.get("error"):
                continue
            try:
                results[symbol] = run_debate_analysis(
                    decision,
                    stock=item,
                    extended_info=info_map.get(symbol, {}),
                    model=AI_MODEL,
                    api_key=AI_API_KEY,
                    base_url=AI_BASE_URL,
                )
            except Exception as exc:
                results[symbol] = {
                    "mode": "a_share_debate",
                    "enabled": True,
                    "error": str(exc),
                    "bull": {},
                    "bear": {},
                    "risk_manager": {},
                }
        return results

    def _render_debate_lines(self, debate: dict[str, Any]) -> list[str]:
        if not debate or not debate.get("enabled"):
            return []
        if debate.get("error"):
            return [f"- **LLM多空辩论**：生成失败，{debate.get('error')}"]
        bull = (debate.get("bull") or {}).get("structured") or {}
        bear = (debate.get("bear") or {}).get("structured") or {}
        manager = (debate.get("risk_manager") or {}).get("structured") or {}
        lines = ["- **LLM多空辩论**："]
        if bull:
            evidence = "；".join((bull.get("证据") or [])[:2])
            lines.append(f"  - 多头：{bull.get('核心论点', '--')}；{evidence}")
        if bear:
            risks = "；".join((bear.get("风险") or [])[:2])
            lines.append(f"  - 空头：{bear.get('核心论点', '--')}；{risks}")
        if manager:
            lines.append(
                f"  - 风控裁决：{manager.get('最终裁决', '--')}，"
                f"仓位 {manager.get('建议仓位', '--')}，置信度 {manager.get('置信度', '--')}；"
                f"{manager.get('核心理由', '')}"
            )
        return lines

    @staticmethod
    def _decision_score(item: dict[str, Any]) -> int:
        score = 50
        signal = str(item.get("signal_summary") or item.get("rating") or "")
        change_pct = item.get("change_pct")
        if "偏多" in signal:
            score += 20
        if "强" in signal:
            score += 10
        if "偏空" in signal:
            score -= 20
        try:
            change_value = float(change_pct or 0)
            if change_value > 3:
                score += 8
            elif change_value < -3:
                score -= 8
        except Exception:
            pass
        return max(0, min(100, score))

    @staticmethod
    def _risk_count(info: dict[str, Any]) -> int:
        risk_events = info.get("risk_events") or {}
        count = 0
        if risk_events.get("lhb"):
            count += 1
        count += len(risk_events.get("restricted_release") or [])
        count += len(risk_events.get("announcements") or [])
        return count

    def _risk_lines(self, risk_events: dict[str, Any]) -> list[str]:
        lines = []
        lhb = risk_events.get("lhb") or {}
        if lhb:
            lines.append(
                f"龙虎榜 {lhb.get('period', '--')} 上榜 {self._fmt_number(lhb.get('times'))} 次，"
                f"净买额 {self._fmt_money(lhb.get('net_amount'))}"
            )
        for item in (risk_events.get("restricted_release") or [])[:2]:
            lines.append(
                f"限售解禁 {item.get('date', '--')}，数量 {self._fmt_number(item.get('shares'))}，"
                f"市值 {self._fmt_money(item.get('market_value'))}"
            )
        for item in (risk_events.get("announcements") or [])[:3]:
            title = item.get("title", "")
            if self._is_risk_announcement(title, item.get("type", "")):
                lines.append(f"公告关注：{title}")
        return lines

    @staticmethod
    def _is_risk_announcement(title: str, category: str = "") -> bool:
        text = f"{title}{category}"
        keywords = ["风险", "减持", "质押", "诉讼", "处罚", "问询", "退市", "停牌", "亏损", "业绩预告"]
        return any(keyword in text for keyword in keywords)

    def _operation_checklist(self, watchlist: list[dict[str, Any]], extended_items: list[dict[str, Any]]) -> list[str]:
        checklist = [
            "先确认大盘温度和所属板块是否同向，避免逆势追高。",
            "若出现偏多信号，优先等待回踩支撑或放量确认，不用一次性满仓。",
            "若出现偏空信号或风险公告，先降仓位或暂停新增。",
        ]
        if any(self._risk_count(item.get("info") or {}) > 0 for item in extended_items):
            checklist.append("存在龙虎榜/解禁/公告事件的标的，盘前先阅读原始公告和成交明细。")
        if not watchlist:
            checklist.append("暂无自选股时，先维护 watchlist.json，再让日报聚焦固定股票池。")
        return checklist

    @staticmethod
    def _fmt_key_values(values: dict[str, Any]) -> str:
        return "；".join(f"{key}={value}" for key, value in list(values.items())[:4])

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
