"""AKShare 扩展信息 provider。"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from data.models import utc_now_iso
from data.providers.akshare_provider import AKSHARE_AVAILABLE, ak, _brief_error, _safe_float
from data.runtime import run_with_timeout


logger = logging.getLogger(__name__)


class AkShareInfoProvider:
    """财务摘要、资金流、新闻等扩展信息接口。"""

    source_name = "AKShare"

    def get_stock_extended_info(self, symbol: str, timeout_seconds: float = 4) -> dict[str, Any]:
        if not AKSHARE_AVAILABLE:
            return self._empty_payload(symbol, "AKShare 不可用")

        return {
            "symbol": symbol,
            "financial": self.get_financial_summary(symbol, timeout_seconds=timeout_seconds),
            "fund_flow": self.get_fund_flow_summary(symbol, timeout_seconds=timeout_seconds),
            "news": self.get_news(symbol, timeout_seconds=timeout_seconds, limit=5),
            "research": self.get_research_summary(symbol, timeout_seconds=timeout_seconds),
            "risk_events": self.get_risk_events(symbol, timeout_seconds=timeout_seconds),
            "sector_attribution": self.get_sector_attribution(symbol, timeout_seconds=timeout_seconds),
            "source": self.source_name,
            "updated_at": utc_now_iso(),
        }

    def get_financial_summary(self, symbol: str, timeout_seconds: float = 4) -> dict[str, Any]:
        try:
            df = run_with_timeout(lambda: ak.stock_financial_abstract(symbol=symbol), timeout_seconds)
            return self._normalize_financial_summary(df)
        except Exception as exc:
            logger.info("获取财务摘要失败 symbol=%s error=%s", symbol, _brief_error(exc))
            return {}

    def get_fund_flow_summary(self, symbol: str, timeout_seconds: float = 4) -> dict[str, Any]:
        try:
            market = "sh" if symbol.startswith("6") else "bj" if symbol.startswith(("4", "8")) else "sz"
            df = run_with_timeout(
                lambda: ak.stock_individual_fund_flow(stock=symbol, market=market),
                timeout_seconds,
            )
            return self._normalize_fund_flow_summary(df)
        except Exception as exc:
            logger.info("获取资金流失败 symbol=%s error=%s", symbol, _brief_error(exc))
            return {}

    def get_news(self, symbol: str, timeout_seconds: float = 4, limit: int = 5) -> list[dict[str, Any]]:
        try:
            df = run_with_timeout(lambda: ak.stock_news_em(symbol=symbol), timeout_seconds)
            return self._normalize_news(df, limit=limit)
        except Exception as exc:
            logger.info("获取个股新闻失败 symbol=%s error=%s", symbol, _brief_error(exc))
            return []

    def get_research_summary(self, symbol: str, timeout_seconds: float = 4) -> dict[str, Any]:
        return {
            "reports": self.get_research_reports(symbol, timeout_seconds=timeout_seconds, limit=5),
            "eps_consensus": self.get_eps_consensus(symbol, timeout_seconds=timeout_seconds),
        }

    def get_research_reports(self, symbol: str, timeout_seconds: float = 4, limit: int = 5) -> list[dict[str, Any]]:
        try:
            df = run_with_timeout(lambda: ak.stock_research_report_em(symbol=symbol), timeout_seconds)
            return self._normalize_research_reports(df, limit=limit)
        except Exception as exc:
            logger.info("获取研报列表失败 symbol=%s error=%s", symbol, _brief_error(exc))
            return []

    def get_eps_consensus(self, symbol: str, timeout_seconds: float = 4) -> dict[str, Any]:
        try:
            df = run_with_timeout(
                lambda: ak.stock_profit_forecast_ths(symbol=symbol, indicator="预测年报每股收益"),
                timeout_seconds,
            )
            return self._normalize_eps_consensus(df)
        except Exception as exc:
            logger.info("获取一致预期 EPS 失败 symbol=%s error=%s", symbol, _brief_error(exc))
            return {}

    def get_risk_events(self, symbol: str, timeout_seconds: float = 4) -> dict[str, Any]:
        return {
            "lhb": self.get_lhb_summary(symbol, timeout_seconds=timeout_seconds),
            "restricted_release": self.get_restricted_release(symbol, timeout_seconds=timeout_seconds),
            "announcements": self.get_announcements(symbol, timeout_seconds=timeout_seconds, limit=5),
        }

    def get_lhb_summary(self, symbol: str, timeout_seconds: float = 4) -> dict[str, Any]:
        try:
            df = run_with_timeout(lambda: ak.stock_lhb_stock_statistic_em(symbol="近一月"), timeout_seconds)
            return self._normalize_lhb_summary(symbol, df)
        except Exception as exc:
            logger.info("获取龙虎榜统计失败 symbol=%s error=%s", symbol, _brief_error(exc))
            return {}

    def get_restricted_release(self, symbol: str, timeout_seconds: float = 4) -> list[dict[str, Any]]:
        try:
            df = run_with_timeout(lambda: ak.stock_restricted_release_queue_em(symbol=symbol), timeout_seconds)
            return self._normalize_restricted_release(df, limit=5)
        except Exception as exc:
            logger.info("获取限售解禁失败 symbol=%s error=%s", symbol, _brief_error(exc))
            return []

    def get_announcements(self, symbol: str, timeout_seconds: float = 4, limit: int = 5) -> list[dict[str, Any]]:
        try:
            end_date = datetime.now().strftime("%Y%m%d")
            begin_date = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
            df = run_with_timeout(
                lambda: ak.stock_individual_notice_report(
                    security=symbol,
                    symbol="全部",
                    begin_date=begin_date,
                    end_date=end_date,
                ),
                timeout_seconds,
            )
            return self._normalize_announcements(df, limit=limit)
        except Exception as exc:
            logger.info("获取个股公告失败 symbol=%s error=%s", symbol, _brief_error(exc))
            return []

    def get_sector_attribution(self, symbol: str, timeout_seconds: float = 4) -> dict[str, Any]:
        try:
            industry_df = run_with_timeout(lambda: ak.stock_board_industry_name_em(), timeout_seconds)
            concept_df = run_with_timeout(lambda: ak.stock_board_concept_name_em(), timeout_seconds)
            return self._find_sector_attribution(symbol, industry_df, concept_df, timeout_seconds=timeout_seconds)
        except Exception as exc:
            logger.info("获取板块归因失败 symbol=%s error=%s", symbol, _brief_error(exc))
            return {"industry": {}, "concepts": []}

    def _empty_payload(self, symbol: str, reason: str) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "financial": {},
            "fund_flow": {},
            "news": [],
            "research": {"reports": [], "eps_consensus": {}},
            "risk_events": {"lhb": {}, "restricted_release": [], "announcements": []},
            "sector_attribution": {"industry": {}, "concepts": []},
            "source": self.source_name,
            "updated_at": utc_now_iso(),
            "error": reason,
        }

    def _normalize_financial_summary(self, df: pd.DataFrame) -> dict[str, Any]:
        if df is None or df.empty or "指标" not in df.columns:
            return {}

        report_columns = [
            col for col in df.columns
            if str(col).isdigit() and len(str(col)) == 8
        ]
        if not report_columns:
            return {}

        latest_period = sorted(report_columns, reverse=True)[0]
        desired_metrics = ["营业总收入", "归母净利润", "扣非净利润", "经营现金流量净额", "每股收益"]
        metrics = {}
        for metric_name in desired_metrics:
            row = df[df["指标"] == metric_name]
            if not row.empty:
                metrics[metric_name] = _safe_float(row.iloc[0].get(latest_period))

        return {
            "period": latest_period,
            "metrics": metrics,
        }

    def _normalize_fund_flow_summary(self, df: pd.DataFrame) -> dict[str, Any]:
        if df is None or df.empty:
            return {}

        latest = df.iloc[-1]
        recent = df.tail(5)
        return {
            "date": str(latest.get("日期", "")),
            "main_net_inflow": _safe_float(latest.get("主力净流入-净额")),
            "main_net_inflow_ratio": _safe_float(latest.get("主力净流入-净占比")),
            "super_large_net_inflow": _safe_float(latest.get("超大单净流入-净额")),
            "large_net_inflow": _safe_float(latest.get("大单净流入-净额")),
            "five_day_main_net_inflow": _safe_float(recent["主力净流入-净额"].sum())
            if "主力净流入-净额" in recent.columns else None,
        }

    def _normalize_news(self, df: pd.DataFrame, limit: int = 5) -> list[dict[str, Any]]:
        if df is None or df.empty:
            return []

        items = []
        for _, row in df.head(limit).iterrows():
            title = row.get("新闻标题") or row.get("标题") or row.get("title")
            if not title:
                continue
            items.append({
                "title": str(title),
                "date": str(row.get("发布时间") or row.get("时间") or row.get("date") or ""),
                "url": str(row.get("新闻链接") or row.get("链接") or row.get("url") or ""),
            })
        return items

    def _normalize_research_reports(self, df: pd.DataFrame, limit: int = 5) -> list[dict[str, Any]]:
        if df is None or df.empty:
            return []

        items = []
        for _, row in df.head(limit).iterrows():
            title = self._first_value(row, ["报告名称", "标题", "REPORT_NAME", "REPORT_TITLE"])
            if not title:
                continue
            items.append({
                "title": str(title),
                "date": str(self._first_value(row, ["报告日期", "日期", "PUBLISH_DATE"]) or ""),
                "org": str(self._first_value(row, ["机构名称", "机构", "ORG_NAME"]) or ""),
                "rating": str(self._first_value(row, ["评级", "投资评级", "RATING"]) or ""),
                "pdf_url": str(self._first_value(row, ["pdf链接", "PDF链接", "PDF_URL", "附件地址"]) or ""),
            })
        return items

    def _normalize_eps_consensus(self, df: pd.DataFrame) -> dict[str, Any]:
        if df is None or df.empty:
            return {}

        latest = df.iloc[0]
        values = {}
        for col in df.columns:
            col_text = str(col)
            if "EPS" in col_text.upper() or "每股收益" in col_text or "预测" in col_text:
                value = _safe_float(latest.get(col))
                if value is not None:
                    values[col_text] = value
        return {
            "source": "同花顺盈利预测",
            "values": values,
            "sample_count": len(df),
        } if values else {}

    def _normalize_lhb_summary(self, symbol: str, df: pd.DataFrame) -> dict[str, Any]:
        if df is None or df.empty:
            return {}
        code_col = self._find_column(df, ["代码", "股票代码"])
        if not code_col:
            return {}
        match = df[df[code_col].astype(str).str.zfill(6) == symbol]
        if match.empty:
            return {}
        row = match.iloc[0]
        return {
            "period": "近一月",
            "times": _safe_float(self._first_value(row, ["上榜次数", "次数"])),
            "buy_amount": _safe_float(self._first_value(row, ["买入额", "买入金额"])),
            "sell_amount": _safe_float(self._first_value(row, ["卖出额", "卖出金额"])),
            "net_amount": _safe_float(self._first_value(row, ["净买额", "净额"])),
            "reason": str(self._first_value(row, ["上榜原因", "原因"]) or ""),
        }

    def _normalize_restricted_release(self, df: pd.DataFrame, limit: int = 5) -> list[dict[str, Any]]:
        if df is None or df.empty:
            return []

        items = []
        for _, row in df.head(limit).iterrows():
            items.append({
                "date": str(self._first_value(row, ["解禁时间", "解禁日期", "上市日期", "日期"]) or ""),
                "shares": _safe_float(self._first_value(row, ["解禁数量", "实际解禁数量", "解禁股数"])),
                "market_value": _safe_float(self._first_value(row, ["实际解禁市值", "解禁市值"])),
                "ratio": _safe_float(self._first_value(row, ["占总股本比例", "占比"])),
                "type": str(self._first_value(row, ["解禁类型", "股份类型", "类型"]) or ""),
            })
        return items

    def _normalize_announcements(self, df: pd.DataFrame, limit: int = 5) -> list[dict[str, Any]]:
        if df is None or df.empty:
            return []

        items = []
        for _, row in df.head(limit).iterrows():
            title = self._first_value(row, ["公告标题", "标题", "公告名称"])
            if not title:
                continue
            items.append({
                "title": str(title),
                "date": str(self._first_value(row, ["公告日期", "日期"]) or ""),
                "type": str(self._first_value(row, ["公告类型", "类型"]) or ""),
                "url": str(self._first_value(row, ["公告链接", "链接", "URL", "url"]) or ""),
            })
        return items

    def _find_sector_attribution(
        self,
        symbol: str,
        industry_df: pd.DataFrame,
        concept_df: pd.DataFrame,
        timeout_seconds: float = 4,
    ) -> dict[str, Any]:
        industry = {}
        concepts = []
        deadline = time.monotonic() + min(max(timeout_seconds, 1), 6)
        lookup_timeout = min(timeout_seconds, 1.5)

        for _, row in (industry_df if industry_df is not None else pd.DataFrame()).head(90).iterrows():
            if time.monotonic() >= deadline:
                break
            name = self._first_value(row, ["板块名称", "行业名称", "名称"])
            if not name:
                continue
            try:
                cons = run_with_timeout(lambda n=str(name): ak.stock_board_industry_cons_em(symbol=n), lookup_timeout)
                if self._contains_symbol(cons, symbol):
                    industry = self._sector_row(row, name)
                    break
            except Exception:
                continue

        for _, row in (concept_df if concept_df is not None else pd.DataFrame()).head(120).iterrows():
            if time.monotonic() >= deadline:
                break
            name = self._first_value(row, ["板块名称", "概念名称", "名称"])
            if not name:
                continue
            try:
                cons = run_with_timeout(lambda n=str(name): ak.stock_board_concept_cons_em(symbol=n), lookup_timeout)
                if self._contains_symbol(cons, symbol):
                    concepts.append(self._sector_row(row, name))
                    if len(concepts) >= 5:
                        break
            except Exception:
                continue

        return {"industry": industry, "concepts": concepts}

    def _contains_symbol(self, df: pd.DataFrame, symbol: str) -> bool:
        if df is None or df.empty:
            return False
        code_col = self._find_column(df, ["代码", "股票代码"])
        if not code_col:
            return False
        return bool((df[code_col].astype(str).str.zfill(6) == symbol).any())

    def _sector_row(self, row: pd.Series, name: str) -> dict[str, Any]:
        return {
            "name": str(name),
            "change_pct": _safe_float(self._first_value(row, ["涨跌幅", "涨跌幅%", "最新涨跌幅"])),
            "leading_stock": str(self._first_value(row, ["领涨股票", "领涨股", "龙头股"]) or ""),
            "reason": self._sector_reason(str(name)),
        }

    @staticmethod
    def _sector_reason(name: str) -> str:
        keyword_map = {
            "人工智能": "AI 主题活跃度影响估值和风险偏好",
            "机器人": "机器人产业链题材催化",
            "芯片": "半导体国产替代和周期预期",
            "银行": "利率、息差和资产质量驱动",
            "证券": "市场成交活跃度和政策预期驱动",
            "新能源": "产业链景气度和政策预期驱动",
            "光伏": "装机需求、价格周期和政策影响",
            "医药": "业绩兑现、集采和创新药催化",
        }
        for keyword, reason in keyword_map.items():
            if keyword in name:
                return reason
        return "相关板块涨跌和资金偏好可能影响短期表现"

    @staticmethod
    def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
        for candidate in candidates:
            for col in df.columns:
                if candidate == str(col) or candidate in str(col):
                    return col
        return None

    @staticmethod
    def _first_value(row: pd.Series, candidates: list[str]) -> Any:
        for candidate in candidates:
            for key, value in row.items():
                if candidate == str(key) or candidate in str(key):
                    if pd.notna(value):
                        return value
        return None
