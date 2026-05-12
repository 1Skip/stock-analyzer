"""AKShare 扩展信息 provider。"""
from __future__ import annotations

import logging
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

    def _empty_payload(self, symbol: str, reason: str) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "financial": {},
            "fund_flow": {},
            "news": [],
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
