"""AKShare 扩展信息 provider。"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
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

    def _try_sources(
        self,
        source_name: str,
        fetchers: list[tuple[str, Any, Any]],
        timeout_seconds: float,
        empty_reason: str = "多源均未返回可用数据",
        return_status_on_failure: bool = True,
    ) -> dict[str, Any]:
        errors = []
        for label, fetcher, normalizer in fetchers:
            try:
                df = run_with_timeout(fetcher, timeout_seconds)
                result = normalizer(df)
                if result:
                    if isinstance(result, dict):
                        result.setdefault("status", "ok")
                        result.setdefault("source", label)
                    return result
                errors.append(f"{label}返回空数据")
            except Exception as exc:
                errors.append(f"{label}失败:{_brief_error(exc)}")
        logger.info("%s 多源获取失败 errors=%s", source_name, " | ".join(errors))
        if not return_status_on_failure:
            return {}
        return {
            "status": "source_failed" if any("失败:" in item for item in errors) else "source_empty",
            "source": source_name,
            "reason": " | ".join(errors) or empty_reason,
        }

    def _try_list_sources(
        self,
        source_name: str,
        fetchers: list[tuple[str, Any, Any]],
        timeout_seconds: float,
    ) -> list[dict[str, Any]]:
        errors = []
        for label, fetcher, normalizer in fetchers:
            try:
                df = run_with_timeout(fetcher, timeout_seconds)
                result = normalizer(df)
                if result:
                    return result
                errors.append(f"{label}返回空数据")
            except Exception as exc:
                errors.append(f"{label}失败:{_brief_error(exc)}")
        logger.info("%s 多源获取失败 errors=%s", source_name, " | ".join(errors))
        return []

    def get_stock_extended_info(
        self,
        symbol: str,
        timeout_seconds: float = 4,
        include_deep_layers: bool = True,
    ) -> dict[str, Any]:
        if not AKSHARE_AVAILABLE:
            return self._empty_payload(symbol, "AKShare 不可用")

        payload = {
            "symbol": symbol,
            "financial": {},
            "fund_flow": {},
            "news": [],
            "market_news": [],
            "research": {"reports": [], "eps_consensus": {}},
            "dividend": {},
            "risk_events": {"lhb": {}, "restricted_release": [], "announcements": []},
            "sector_attribution": {"industry": {}, "concepts": []},
            "source": self.source_name,
            "updated_at": utc_now_iso(),
        }
        tasks = {
            "financial": lambda: self.get_financial_summary(symbol, timeout_seconds=timeout_seconds),
            "fund_flow": lambda: self.get_fund_flow_summary(symbol, timeout_seconds=timeout_seconds),
            "news": lambda: self.get_news(symbol, timeout_seconds=timeout_seconds, limit=5),
            "market_news": lambda: self.get_market_news(timeout_seconds=timeout_seconds, limit=8),
        }
        if include_deep_layers:
            tasks.update({
                "research": lambda: self.get_research_summary(symbol, timeout_seconds=timeout_seconds),
                "dividend": lambda: self.get_dividend_summary(symbol, timeout_seconds=timeout_seconds),
                "risk_events": lambda: self.get_risk_events(symbol, timeout_seconds=timeout_seconds),
                "sector_attribution": lambda: self.get_sector_attribution(symbol, timeout_seconds=timeout_seconds),
            })
        executor = ThreadPoolExecutor(max_workers=len(tasks))
        futures = {key: executor.submit(task) for key, task in tasks.items()}
        deadline = time.monotonic() + max(timeout_seconds, 1)
        try:
            for key, future in futures.items():
                remaining = max(deadline - time.monotonic(), 0)
                if remaining <= 0:
                    break
                try:
                    result = future.result(timeout=remaining)
                    if result:
                        payload[key] = result
                except TimeoutError:
                    logger.info("获取扩展信息部分超时 symbol=%s field=%s", symbol, key)
                except Exception as exc:
                    logger.info("获取扩展信息部分失败 symbol=%s field=%s error=%s", symbol, key, _brief_error(exc))
        finally:
            for future in futures.values():
                if not future.done():
                    future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
        return payload

    def get_financial_summary(self, symbol: str, timeout_seconds: float = 4) -> dict[str, Any]:
        em_symbol = f"{symbol}.SH" if symbol.startswith("6") else f"{symbol}.SZ"
        return self._try_sources(
            "财务摘要",
            [
                ("东方财富财务摘要", lambda: ak.stock_financial_abstract(symbol=symbol), self._normalize_financial_summary),
                ("同花顺财务摘要", lambda: ak.stock_financial_abstract_ths(symbol=symbol, indicator="按报告期"), self._normalize_financial_summary),
                ("同花顺新版财务摘要", lambda: ak.stock_financial_abstract_new_ths(symbol=symbol, indicator="按报告期"), self._normalize_financial_summary),
                ("东方财富财务指标", lambda: ak.stock_financial_analysis_indicator_em(symbol=em_symbol, indicator="按报告期"), self._normalize_financial_indicator_em),
                ("新浪利润表", lambda: ak.stock_financial_report_sina(stock=self._sina_stock_code(symbol), symbol="利润表"), self._normalize_sina_profit_statement),
            ],
            timeout_seconds,
        )

    def get_fund_flow_summary(self, symbol: str, timeout_seconds: float = 4) -> dict[str, Any]:
        market = "sh" if symbol.startswith("6") else "bj" if symbol.startswith(("4", "8")) else "sz"
        return self._try_sources(
            "资金流",
            [
                ("东方财富个股资金流", lambda: ak.stock_individual_fund_flow(stock=symbol, market=market), self._normalize_fund_flow_summary),
                ("东方财富主力资金流", lambda: ak.stock_main_fund_flow(symbol="全部股票"), lambda df: self._normalize_main_fund_flow(symbol, df)),
                ("东方财富即时资金流", lambda: ak.stock_fund_flow_individual(symbol="即时"), lambda df: self._normalize_fund_flow_snapshot(symbol, df)),
            ],
            timeout_seconds,
        )

    def get_news(self, symbol: str, timeout_seconds: float = 4, limit: int = 5) -> list[dict[str, Any]]:
        return self._try_list_sources(
            "个股新闻",
            [
                ("东方财富个股新闻", lambda: self._fetch_stock_news_em(symbol), lambda df: self._normalize_news(df, limit=limit, source="东方财富个股新闻")),
                ("财联社A股电报", lambda: ak.stock_info_global_cls(symbol="全部"), lambda df: self._normalize_filtered_market_news(symbol, df, limit=limit, source="财联社资讯")),
            ],
            timeout_seconds,
        )

    @staticmethod
    def _fetch_stock_news_em(symbol: str) -> pd.DataFrame:
        with pd.option_context("mode.string_storage", "python"):
            return ak.stock_news_em(symbol=symbol)

    def get_market_news(self, timeout_seconds: float = 4, limit: int = 8) -> list[dict[str, Any]]:
        """获取全局市场资讯/催化消息，多源聚合。"""
        items = []
        errors = []
        sources = [
            ("财新数据通", lambda: ak.stock_news_main_cx(), lambda df: self._normalize_market_news(df, limit=limit, source="财新数据通")),
            ("财联社资讯", lambda: ak.stock_info_global_cls(symbol="全部"), lambda df: self._normalize_market_news(df, limit=limit, source="财联社资讯")),
        ]
        for label, fetcher, normalizer in sources:
            try:
                df = run_with_timeout(fetcher, timeout_seconds)
                items.extend(normalizer(df))
            except Exception as exc:
                errors.append(f"{label}失败:{_brief_error(exc)}")
        if errors and not items:
            logger.info("获取市场资讯失败 errors=%s", " | ".join(errors))
        return self._dedupe_news(items, limit=limit)

    def get_research_summary(self, symbol: str, timeout_seconds: float = 4) -> dict[str, Any]:
        return {
            "reports": self.get_research_reports(symbol, timeout_seconds=timeout_seconds, limit=5),
            "eps_consensus": self.get_eps_consensus(symbol, timeout_seconds=timeout_seconds),
        }

    def get_dividend_summary(self, symbol: str, timeout_seconds: float = 4) -> dict[str, Any]:
        errors = []
        try:
            df = run_with_timeout(lambda: ak.stock_dividend_cninfo(symbol=symbol), timeout_seconds)
            result = self._normalize_cninfo_dividend_summary(df)
            if result:
                return result
            errors.append("巨潮返回空数据")
        except Exception as exc:
            errors.append(f"巨潮失败:{_brief_error(exc)}")

        try:
            df = run_with_timeout(
                lambda: ak.stock_history_dividend_detail(symbol=symbol, indicator="分红"),
                timeout_seconds,
            )
            result = self._normalize_sina_dividend_detail(df)
            if result:
                return result
            errors.append("新浪明细返回空数据")
        except Exception as exc:
            errors.append(f"新浪明细失败:{_brief_error(exc)}")

        try:
            df = run_with_timeout(lambda: ak.stock_history_dividend(), timeout_seconds)
            result = self._normalize_sina_dividend_overview(symbol, df)
            if result:
                return result
            errors.append("新浪全市场摘要返回空数据")
        except Exception as exc:
            errors.append(f"新浪全市场失败:{_brief_error(exc)}")

        logger.info("获取历史分红失败 symbol=%s errors=%s", symbol, " | ".join(errors))
        return {"status": "source_failed", "source": "巨潮/新浪分红", "reason": " | ".join(errors)}

    def get_research_reports(self, symbol: str, timeout_seconds: float = 4, limit: int = 5) -> list[dict[str, Any]]:
        return self._try_list_sources(
            "研报列表",
            [
                ("东方财富个股研报", lambda: ak.stock_research_report_em(symbol=symbol), lambda df: self._normalize_research_reports(df, limit=limit)),
                ("东方财富盈利预测", lambda: ak.stock_profit_forecast_em(symbol=symbol), lambda df: self._normalize_forecast_as_reports(df, limit=limit)),
            ],
            timeout_seconds,
        )

    def get_eps_consensus(self, symbol: str, timeout_seconds: float = 4) -> dict[str, Any]:
        errors = []
        try:
            df = run_with_timeout(
                lambda: ak.stock_profit_forecast_ths(symbol=symbol, indicator="预测年报每股收益"),
                timeout_seconds,
            )
            result = self._normalize_eps_consensus(df)
            if result:
                return result
            errors.append("同花顺盈利预测返回空数据")
        except Exception as exc:
            logger.info("获取一致预期 EPS 失败 symbol=%s error=%s", symbol, _brief_error(exc))
            errors.append(f"同花顺盈利预测失败:{_brief_error(exc)}")

        try:
            df = run_with_timeout(lambda: ak.stock_profit_forecast_em(symbol=symbol), timeout_seconds)
            result = self._normalize_eps_consensus_em(df)
            if result:
                return result
            errors.append("东方财富盈利预测返回空数据")
        except Exception as exc:
            errors.append(f"东方财富盈利预测失败:{_brief_error(exc)}")

        return {
            "status": "source_failed" if any("失败:" in item for item in errors) else "source_empty",
            "source": "同花顺/东方财富盈利预测",
            "reason": " | ".join(errors) or "多源均未返回可计算EPS字段",
        }

    def get_risk_events(self, symbol: str, timeout_seconds: float = 4) -> dict[str, Any]:
        return {
            "lhb": self.get_lhb_summary(symbol, timeout_seconds=timeout_seconds),
            "restricted_release": self.get_restricted_release(symbol, timeout_seconds=timeout_seconds),
            "announcements": self.get_announcements(symbol, timeout_seconds=timeout_seconds, limit=5),
        }

    def get_lhb_summary(self, symbol: str, timeout_seconds: float = 4) -> dict[str, Any]:
        return self._try_sources(
            "龙虎榜",
            [
                ("东方财富龙虎榜统计", lambda: ak.stock_lhb_stock_statistic_em(symbol="近一月"), lambda df: self._normalize_lhb_summary(symbol, df)),
                ("新浪龙虎榜个股统计", lambda: ak.stock_lhb_ggtj_sina(symbol="30"), lambda df: self._normalize_lhb_summary(symbol, df)),
            ],
            timeout_seconds,
            return_status_on_failure=False,
        )

    def get_restricted_release(self, symbol: str, timeout_seconds: float = 4) -> list[dict[str, Any]]:
        return self._try_list_sources(
            "限售解禁",
            [
                ("东方财富限售解禁", lambda: ak.stock_restricted_release_queue_em(symbol=symbol), lambda df: self._normalize_restricted_release(df, limit=5, source="东方财富限售解禁")),
                ("新浪限售解禁", lambda: ak.stock_restricted_release_queue_sina(symbol=symbol), lambda df: self._normalize_restricted_release(df, limit=5, source="新浪限售解禁")),
            ],
            timeout_seconds,
        )

    def get_announcements(self, symbol: str, timeout_seconds: float = 4, limit: int = 5) -> list[dict[str, Any]]:
        end_date = datetime.now().strftime("%Y%m%d")
        begin_date = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
        return self._try_list_sources(
            "公告",
            [
                (
                    "东方财富个股公告",
                    lambda: ak.stock_individual_notice_report(
                        security=symbol,
                        symbol="全部",
                        begin_date=begin_date,
                        end_date=end_date,
                    ),
                    lambda df: self._normalize_announcements(df, limit=limit, source="东方财富个股公告"),
                ),
                (
                    "东方财富全市场公告",
                    lambda: ak.stock_notice_report(symbol="全部", date=end_date),
                    lambda df: self._normalize_notice_report(symbol, df, limit=limit),
                ),
            ],
            timeout_seconds,
        )

    def _get_announcements_single_source(self, symbol: str, timeout_seconds: float = 4, limit: int = 5) -> list[dict[str, Any]]:
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
        errors = []
        source_groups = [
            (
                "东方财富板块",
                lambda: ak.stock_board_industry_name_em(),
                lambda: ak.stock_board_concept_name_em(),
                lambda name: ak.stock_board_industry_cons_em(symbol=name),
                lambda name: ak.stock_board_concept_cons_em(symbol=name),
            ),
            (
                "同花顺板块",
                lambda: ak.stock_board_industry_name_ths(),
                lambda: ak.stock_board_concept_name_ths(),
                lambda name: ak.stock_board_industry_info_ths(symbol=name),
                lambda name: ak.stock_board_concept_info_ths(symbol=name),
            ),
        ]
        for source, industry_fetcher, concept_fetcher, industry_cons_fetcher, concept_cons_fetcher in source_groups:
            try:
                industry_df = run_with_timeout(industry_fetcher, timeout_seconds)
                concept_df = run_with_timeout(concept_fetcher, timeout_seconds)
                result = self._find_sector_attribution(
                    symbol,
                    industry_df,
                    concept_df,
                    timeout_seconds=timeout_seconds,
                    source=source,
                    industry_cons_fetcher=industry_cons_fetcher,
                    concept_cons_fetcher=concept_cons_fetcher,
                )
                if result.get("industry") or result.get("concepts"):
                    return result
                errors.append(f"{source}返回空归因")
            except Exception as exc:
                errors.append(f"{source}失败:{_brief_error(exc)}")
        logger.info("获取板块归因失败 symbol=%s errors=%s", symbol, " | ".join(errors))
        return {"industry": {}, "concepts": [], "status": "source_failed", "source": "东财/同花顺板块", "reason": " | ".join(errors)}

    def _empty_payload(self, symbol: str, reason: str) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "financial": {},
            "fund_flow": {},
            "news": [],
            "market_news": [],
            "research": {"reports": [], "eps_consensus": {}},
            "dividend": {},
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

        history = self._financial_history_from_wide_rows(df, report_columns, desired_metrics, label_col=df.columns[0])
        return {
            "period": latest_period,
            "metrics": metrics,
            "history": history,
        }

    def _normalize_financial_indicator_em(self, df: pd.DataFrame) -> dict[str, Any]:
        if df is None or df.empty:
            return {}
        rows = df.copy()
        date_col = self._find_column(rows, ["REPORT_DATE", "报告期", "日期"])
        if date_col:
            rows["_sort_date"] = pd.to_datetime(rows[date_col], errors="coerce")
            rows = rows.sort_values("_sort_date", ascending=False)
        latest = rows.iloc[0]
        metrics = {}
        mapping = {
            "营业总收入": ["营业总收入", "TOTAL_OPERATE_INCOME"],
            "归母净利润": ["归母净利润", "PARENT_NETPROFIT", "净利润"],
            "扣非净利润": ["扣非净利润", "DEDUCT_PARENT_NETPROFIT"],
            "经营现金流量净额": ["经营现金流量净额", "NETCASH_OPERATE"],
            "每股收益": ["每股收益", "EPSJB", "基本每股收益"],
        }
        for target, candidates in mapping.items():
            value = _safe_float(self._first_value(latest, candidates))
            if value is not None:
                metrics[target] = value
        if not metrics:
            return {}
        history = self._financial_history_from_records(rows, date_col, mapping)
        return {
            "period": str(self._first_value(latest, [date_col or "", "REPORT_DATE", "报告期", "日期"]) or ""),
            "metrics": metrics,
            "history": history,
        }

    def _normalize_sina_profit_statement(self, df: pd.DataFrame) -> dict[str, Any]:
        if df is None or df.empty:
            return {}
        rows = df.copy()
        period_columns = [col for col in rows.columns if str(col).isdigit() and len(str(col)) >= 6]
        if not period_columns:
            period_columns = [col for col in rows.columns if str(col) not in {"报表日期", "项目", "指标"}]
        if not period_columns:
            return {}
        latest_period = sorted([str(col) for col in period_columns], reverse=True)[0]
        label_col = self._find_column(rows, ["报表日期", "项目", "指标"]) or rows.columns[0]
        mapping = {
            "营业总收入": ["营业总收入", "营业收入"],
            "归母净利润": ["归属于母公司所有者的净利润", "归母净利润", "净利润"],
            "每股收益": ["基本每股收益", "每股收益"],
        }
        metrics = {}
        for target, aliases in mapping.items():
            matched = rows[rows[label_col].astype(str).apply(lambda text: any(alias in text for alias in aliases))]
            if not matched.empty:
                value = _safe_float(matched.iloc[0].get(latest_period))
                if value is not None:
                    metrics[target] = value
        history = self._financial_history_from_wide_rows(
            rows,
            period_columns,
            list(mapping.keys()),
            label_col=label_col,
        )
        return {"period": latest_period, "metrics": metrics, "history": history} if metrics else {}

    def _financial_history_from_wide_rows(self, df: pd.DataFrame, period_columns: list[Any], metric_names: list[str], label_col: str | None = None) -> list[dict[str, Any]]:
        label_col = label_col or df.columns[0]
        history = []
        for period in sorted([str(col) for col in period_columns])[-4:]:
            row_payload: dict[str, Any] = {"period": period}
            for metric_name in metric_names:
                rows = df[df[label_col].astype(str).apply(lambda text: metric_name == text or metric_name in text)]
                if rows.empty:
                    continue
                value = _safe_float(rows.iloc[0].get(period))
                if value is not None:
                    row_payload[metric_name] = value
            if len(row_payload) > 1:
                history.append(row_payload)
        return history

    def _financial_history_from_records(self, df: pd.DataFrame, date_col: str | None, mapping: dict[str, list[str]]) -> list[dict[str, Any]]:
        if df is None or df.empty:
            return []
        rows = df.copy()
        if date_col:
            rows = rows.sort_values(date_col).tail(4)
        else:
            rows = rows.tail(4)
        history = []
        for _, row in rows.iterrows():
            row_payload: dict[str, Any] = {
                "period": str(self._first_value(row, [date_col or "", "REPORT_DATE", "?????", "???"]) or "")
            }
            for target, candidates in mapping.items():
                value = _safe_float(self._first_value(row, candidates))
                if value is not None:
                    row_payload[target] = value
            if len(row_payload) > 1:
                history.append(row_payload)
        return history

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

    def _normalize_main_fund_flow(self, symbol: str, df: pd.DataFrame) -> dict[str, Any]:
        if df is None or df.empty:
            return {}
        code_col = self._find_column(df, ["代码", "股票代码"])
        if not code_col:
            return {}
        rows = df[df[code_col].astype(str).str.zfill(6) == str(symbol).zfill(6)]
        if rows.empty:
            return {}
        row = rows.iloc[0]
        return {
            "date": str(self._first_value(row, ["日期", "最新"]) or ""),
            "main_net_inflow": _safe_float(self._first_value(row, ["主力净流入-净额", "今日主力净流入", "主力净流入"])),
            "main_net_inflow_ratio": _safe_float(self._first_value(row, ["主力净流入-净占比", "今日主力净占比", "主力净占比"])),
            "super_large_net_inflow": _safe_float(self._first_value(row, ["超大单净流入", "超大单净额"])),
            "large_net_inflow": _safe_float(self._first_value(row, ["大单净流入", "大单净额"])),
            "source_note": "主力资金全市场快照；近5日字段可能不可用",
        }

    def _normalize_fund_flow_snapshot(self, symbol: str, df: pd.DataFrame) -> dict[str, Any]:
        if df is None or df.empty:
            return {}
        code_col = self._find_column(df, ["代码", "股票代码"])
        if not code_col:
            return {}
        rows = df[df[code_col].astype(str).str.zfill(6) == str(symbol).zfill(6)]
        if rows.empty:
            return {}
        row = rows.iloc[0]
        return {
            "date": str(self._first_value(row, ["日期", "更新时间"]) or ""),
            "main_net_inflow": _safe_float(self._first_value(row, ["主力净流入", "净额", "资金净流入"])),
            "main_net_inflow_ratio": _safe_float(self._first_value(row, ["主力净占比", "净占比", "资金净占比"])),
            "source_note": "即时资金流快照；口径不同于历史资金流",
        }

    def _normalize_news(self, df: pd.DataFrame, limit: int = 5, source: str = "") -> list[dict[str, Any]]:
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
                "source": source,
            })
        return items

    def _normalize_market_news(self, df: pd.DataFrame, limit: int = 8, source: str = "财新数据通") -> list[dict[str, Any]]:
        if df is None or df.empty:
            return []

        items = []
        for _, row in df.head(limit).iterrows():
            summary = self._first_value(row, ["summary", "摘要", "内容", "新闻内容"])
            title = self._first_value(row, ["title", "标题", "新闻标题"]) or summary
            if not title:
                continue
            items.append({
                "title": str(title),
                "summary": str(summary or title),
                "tag": str(self._first_value(row, ["tag", "标签", "分类"]) or "市场动态"),
                "date": str(self._first_value(row, ["date", "时间", "发布时间"]) or ""),
                "url": str(self._first_value(row, ["url", "链接", "新闻链接"]) or ""),
                "source": source,
            })
        return items

    def _normalize_filtered_market_news(self, symbol: str, df: pd.DataFrame, limit: int = 5, source: str = "") -> list[dict[str, Any]]:
        if df is None or df.empty:
            return []
        normalized = self._normalize_market_news(df, limit=max(limit * 4, 20), source=source)
        keyword = str(symbol).zfill(6)
        filtered = [
            item for item in normalized
            if keyword in str(item.get("title", "")) or keyword in str(item.get("summary", ""))
        ]
        return filtered[:limit]

    @staticmethod
    def _dedupe_news(items: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
        seen = set()
        deduped = []
        for item in items:
            title = str(item.get("title") or item.get("summary") or "").strip()
            if not title or title in seen:
                continue
            seen.add(title)
            deduped.append(item)
            if len(deduped) >= limit:
                break
        return deduped

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

    def _normalize_forecast_as_reports(self, df: pd.DataFrame, limit: int = 5) -> list[dict[str, Any]]:
        if df is None or df.empty:
            return []
        items = []
        for _, row in df.head(limit).iterrows():
            org = self._first_value(row, ["机构名称", "机构", "ORG_NAME"])
            rating = self._first_value(row, ["评级", "投资评级", "RATING"])
            date = self._first_value(row, ["报告日期", "日期", "PUBLISH_DATE", "预测日期"])
            if not org and not rating:
                continue
            items.append({
                "title": f"{org or '机构'}盈利预测/评级",
                "date": str(date or ""),
                "org": str(org or ""),
                "rating": str(rating or ""),
                "pdf_url": "",
                "source": "东方财富盈利预测",
            })
        return items

    def _normalize_eps_consensus(self, df: pd.DataFrame) -> dict[str, Any]:
        if df is None or df.empty:
            return {}

        latest = df.iloc[0]
        values = {}
        for col in df.columns:
            col_text = str(col)
            if any(skip in col_text for skip in ("机构数", "机构家数", "预测机构")):
                continue
            if "EPS" in col_text.upper() or "每股收益" in col_text:
                value = _safe_float(latest.get(col))
                if value is not None:
                    values[col_text] = value
        return {
            "source": "同花顺盈利预测",
            "values": values,
            "sample_count": len(df),
        } if values else {}

    def _normalize_eps_consensus_em(self, df: pd.DataFrame) -> dict[str, Any]:
        if df is None or df.empty:
            return {}
        latest = df.iloc[0]
        values = {}
        for col in df.columns:
            col_text = str(col)
            if any(skip in col_text for skip in ("机构数", "机构家数", "预测机构")):
                continue
            if "EPS" in col_text.upper() or "每股收益" in col_text or "预测每股收益" in col_text:
                value = _safe_float(latest.get(col))
                if value is not None:
                    values[col_text] = value
        if not values:
            for col in df.columns:
                col_text = str(col)
                if any(token in col_text for token in ("202", "203")) and any(token in col_text for token in ("收益", "EPS")):
                    value = _safe_float(latest.get(col))
                    if value is not None:
                        values[col_text] = value
        return {
            "status": "ok",
            "source": "东方财富盈利预测",
            "values": values,
            "sample_count": len(df),
        } if values else {}

    def _normalize_cninfo_dividend_summary(self, df: pd.DataFrame) -> dict[str, Any]:
        if df is None or df.empty:
            return {}
        rows = df.copy()
        if "实施方案公告日期" in rows.columns:
            rows["_sort_date"] = pd.to_datetime(rows["实施方案公告日期"], errors="coerce")
            rows = rows.sort_values("_sort_date", ascending=False)
        cash_dividend = _safe_float(self._first_value(rows.iloc[0], ["派息比例", "派息"]))
        if cash_dividend is None:
            return {}
        return {
            "status": "ok",
            "source": "巨潮资讯历史分红",
            "cash_dividend_per_10": cash_dividend,
            "cash_dividend_per_share": cash_dividend / 10,
            "announcement_date": str(self._first_value(rows.iloc[0], ["实施方案公告日期", "公告日期"]) or ""),
            "ex_dividend_date": str(self._first_value(rows.iloc[0], ["除权日", "除权除息日"]) or ""),
            "progress": "实施",
            "description": str(self._first_value(rows.iloc[0], ["实施方案分红说明", "分红说明"]) or ""),
        }

    def _normalize_sina_dividend_detail(self, df: pd.DataFrame) -> dict[str, Any]:
        if df is None or df.empty:
            return {}
        rows = df.copy()
        if "派息" not in rows.columns:
            return {}
        if "进度" in rows.columns:
            implemented = rows[rows["进度"].astype(str).str.contains("实施", na=False)]
            if not implemented.empty:
                rows = implemented
        cash_dividend = _safe_float(rows.iloc[0].get("派息"))
        if cash_dividend is None:
            return {}
        return {
            "status": "ok",
            "source": "新浪财经历史分红",
            "cash_dividend_per_10": cash_dividend,
            "cash_dividend_per_share": cash_dividend / 10,
            "announcement_date": str(rows.iloc[0].get("公告日期") or ""),
            "ex_dividend_date": str(rows.iloc[0].get("除权除息日") or ""),
            "progress": str(rows.iloc[0].get("进度") or ""),
        }

    def _normalize_sina_dividend_overview(self, symbol: str, df: pd.DataFrame) -> dict[str, Any]:
        if df is None or df.empty or "代码" not in df.columns:
            return {}
        rows = df[df["代码"].astype(str).str.zfill(6) == str(symbol).zfill(6)]
        if rows.empty:
            return {}
        row = rows.iloc[0]
        annual_dividend = _safe_float(row.get("年均股息"))
        if annual_dividend is None:
            return {}
        return {
            "status": "ok",
            "source": "新浪财经历史分红摘要",
            "annual_dividend_per_10": annual_dividend,
            "annual_dividend_per_share": annual_dividend / 10,
            "dividend_count": _safe_float(row.get("分红次数")),
            "note": "年均股息摘要，非最近一期现金分红",
        }

    def _normalize_dividend_summary(self, df: pd.DataFrame) -> dict[str, Any]:
        return self._normalize_sina_dividend_detail(df)

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

    def _normalize_restricted_release(self, df: pd.DataFrame, limit: int = 5, source: str = "") -> list[dict[str, Any]]:
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
                "source": source,
            })
        return items

    def _normalize_announcements(self, df: pd.DataFrame, limit: int = 5, source: str = "") -> list[dict[str, Any]]:
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
                "source": source,
            })
        return items

    def _normalize_notice_report(self, symbol: str, df: pd.DataFrame, limit: int = 5) -> list[dict[str, Any]]:
        if df is None or df.empty:
            return []
        code_col = self._find_column(df, ["代码", "股票代码", "证券代码"])
        rows = df
        if code_col:
            rows = df[df[code_col].astype(str).str.zfill(6) == str(symbol).zfill(6)]
        elif "代码" not in df.columns:
            rows = df[df.astype(str).apply(lambda row: row.str.contains(str(symbol).zfill(6), regex=False).any(), axis=1)]
        return self._normalize_announcements(rows, limit=limit, source="东方财富全市场公告")

    def _find_sector_attribution(
        self,
        symbol: str,
        industry_df: pd.DataFrame,
        concept_df: pd.DataFrame,
        timeout_seconds: float = 4,
        source: str = "东方财富板块",
        industry_cons_fetcher: Any | None = None,
        concept_cons_fetcher: Any | None = None,
    ) -> dict[str, Any]:
        industry = {}
        concepts = []
        deadline = time.monotonic() + min(max(timeout_seconds, 1), 6)
        lookup_timeout = min(timeout_seconds, 1.5)
        industry_cons_fetcher = industry_cons_fetcher or (lambda name: ak.stock_board_industry_cons_em(symbol=name))
        concept_cons_fetcher = concept_cons_fetcher or (lambda name: ak.stock_board_concept_cons_em(symbol=name))

        for _, row in (industry_df if industry_df is not None else pd.DataFrame()).head(90).iterrows():
            if time.monotonic() >= deadline:
                break
            name = self._first_value(row, ["板块名称", "行业名称", "名称"])
            if not name:
                continue
            try:
                cons = run_with_timeout(lambda n=str(name): industry_cons_fetcher(n), lookup_timeout)
                if self._contains_symbol(cons, symbol):
                    industry = self._sector_row(row, name, source=source)
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
                cons = run_with_timeout(lambda n=str(name): concept_cons_fetcher(n), lookup_timeout)
                if self._contains_symbol(cons, symbol):
                    concepts.append(self._sector_row(row, name, source=source))
                    if len(concepts) >= 5:
                        break
            except Exception:
                continue

        return {"industry": industry, "concepts": concepts, "source": source}

    def _contains_symbol(self, df: pd.DataFrame, symbol: str) -> bool:
        if df is None or df.empty:
            return False
        code_col = self._find_column(df, ["代码", "股票代码"])
        if not code_col:
            return False
        return bool((df[code_col].astype(str).str.zfill(6) == symbol).any())

    def _sector_row(self, row: pd.Series, name: str, source: str = "") -> dict[str, Any]:
        return {
            "name": str(name),
            "change_pct": _safe_float(self._first_value(row, ["涨跌幅", "涨跌幅%", "最新涨跌幅"])),
            "leading_stock": str(self._first_value(row, ["领涨股票", "领涨股", "龙头股"]) or ""),
            "reason": self._sector_reason(str(name)),
            "source": source,
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
