"""AKShare/CNInfo corporate-action history for A-share accounting."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import logging
from typing import Any, Callable

import pandas as pd

from data.models import utc_now_iso
from data.providers.akshare_provider import AKSHARE_AVAILABLE, ak, _brief_error
from data.runtime import run_with_timeout


logger = logging.getLogger(__name__)


class AkShareCorporateActionProvider:
    """Load implemented dividends, bonus shares, and rights issues from CNInfo."""

    source_name = "巨潮资讯/AKShare"

    def get_events(
        self,
        symbol: str,
        *,
        timeout_seconds: float = 12,
        retries: int = 2,
    ) -> dict[str, Any]:
        symbol_text = str(symbol or "").strip().zfill(6)
        if not symbol_text.isdigit() or len(symbol_text) != 6:
            return self._failed(symbol_text, ["股票代码无效"])
        if not AKSHARE_AVAILABLE or ak is None:
            return self._failed(symbol_text, ["AKShare 不可用"])

        events: list[dict[str, Any]] = []
        errors: list[str] = []
        source_status: dict[str, str] = {}
        sources = (
            (
                "dividend",
                "巨潮资讯历史分红",
                lambda: ak.stock_dividend_cninfo(symbol=symbol_text),
                lambda frame: self.normalize_dividend_events(symbol_text, frame),
            ),
            (
                "rights_issue",
                "巨潮资讯配股实施方案",
                lambda: ak.stock_allotment_cninfo(symbol=symbol_text),
                lambda frame: self.normalize_rights_issue_events(symbol_text, frame),
            ),
        )
        successful_sources = 0
        for key, label, fetcher, normalizer in sources:
            try:
                frame = self._fetch_with_retries(
                    fetcher,
                    timeout_seconds=timeout_seconds,
                    retries=retries,
                    label=label,
                )
                events.extend(normalizer(frame))
                source_status[key] = "ok"
                successful_sources += 1
            except Exception as exc:
                source_status[key] = "failed"
                errors.append(f"{label}失败:{_brief_error(exc)}")

        events = _dedupe_events(events)
        status = (
            "ok"
            if successful_sources == len(sources)
            else "partial_failed"
            if successful_sources
            else "source_failed"
        )
        result = {
            "status": status,
            "symbol": symbol_text,
            "source": self.source_name,
            "fetched_at": utc_now_iso(),
            "events": events,
            "event_count": len(events),
            "source_status": source_status,
            "errors": errors,
        }
        if errors:
            logger.info("公司行为数据不完整 symbol=%s errors=%s", symbol_text, " | ".join(errors))
        return result

    @staticmethod
    def normalize_dividend_events(symbol: str, frame: pd.DataFrame) -> list[dict[str, Any]]:
        required = {"除权日", "股权登记日"}
        _validate_frame(frame, required, "历史分红")
        events: list[dict[str, Any]] = []
        for _, row in frame.iterrows():
            ex_date = _date_text(_row_value(row, "除权日", "除权除息日"))
            if not ex_date:
                continue
            announcement_date = _date_text(_row_value(row, "实施方案公告日期", "公告日期"))
            record_date = _date_text(_row_value(row, "股权登记日"))
            payment_date = _date_text(_row_value(row, "派息日"))
            shares_credit_date = _date_text(_row_value(row, "股份到账日", "红股上市日"))
            report_period = _text(_row_value(row, "报告时间"))
            description = _text(_row_value(row, "实施方案分红说明", "分红说明"))
            common = {
                "symbol": symbol,
                "announcement_date": announcement_date,
                "record_date": record_date,
                "ex_date": ex_date,
                "effective_date": ex_date,
                "payment_date": payment_date,
                "shares_credit_date": shares_credit_date,
                "report_period": report_period,
                "description": description,
                "source": "巨潮资讯历史分红/AKShare",
                "data_status": "verified",
                "accounting_date_basis": "除权日确认权益",
            }

            cash_per_10 = _number(_row_value(row, "派息比例", "派息"))
            if cash_per_10 is not None and cash_per_10 > 0:
                event = {
                    **common,
                    "action_type": "cash_dividend",
                    "cash_per_10_shares": cash_per_10,
                    "cash_per_share": cash_per_10 / 10,
                }
                event["action_id"] = _action_id(event)
                events.append(event)

            bonus_per_10 = _number(_row_value(row, "送股比例", "送股")) or 0.0
            transfer_per_10 = _number(_row_value(row, "转增比例", "转增")) or 0.0
            additional_per_share = (bonus_per_10 + transfer_per_10) / 10
            if additional_per_share > 0:
                event = {
                    **common,
                    "action_type": "share_distribution",
                    "bonus_shares_per_10": bonus_per_10,
                    "transfer_shares_per_10": transfer_per_10,
                    "additional_shares_per_share": additional_per_share,
                }
                event["action_id"] = _action_id(event)
                events.append(event)
        return sorted(events, key=_event_sort_key)

    @staticmethod
    def normalize_rights_issue_events(symbol: str, frame: pd.DataFrame) -> list[dict[str, Any]]:
        required = {"配股比例", "配股价格", "股权登记日"}
        _validate_frame(frame, required, "配股实施方案")
        events: list[dict[str, Any]] = []
        for _, row in frame.iterrows():
            record_date = _date_text(_row_value(row, "股权登记日"))
            ex_date = _date_text(_row_value(row, "除权基准日", "除权日"))
            effective_date = record_date or ex_date
            ratio_per_10 = _number(_row_value(row, "配股比例", "配股方案"))
            rights_price = _number(_row_value(row, "配股价格"))
            if not effective_date or ratio_per_10 is None or ratio_per_10 <= 0 or rights_price is None:
                continue
            event = {
                "symbol": symbol,
                "action_type": "rights_issue",
                "source_event_id": _text(_row_value(row, "记录标识")),
                "announcement_date": _date_text(_row_value(row, "公告日期")),
                "record_date": record_date,
                "ex_date": ex_date,
                "effective_date": effective_date,
                "subscription_start_date": _date_text(_row_value(row, "配股缴款起始日", "缴款起始日")),
                "subscription_end_date": _date_text(_row_value(row, "配股缴款截止日", "缴款终止日")),
                "listing_date": _date_text(_row_value(row, "配股上市日")),
                "rights_per_10_shares": ratio_per_10,
                "rights_per_share": ratio_per_10 / 10,
                "rights_price": rights_price,
                "source": "巨潮资讯配股实施方案/AKShare",
                "data_status": "verified",
                "accounting_date_basis": "股权登记日记录权利，不自动认购",
            }
            event["action_id"] = _action_id(event)
            events.append(event)
        return sorted(events, key=_event_sort_key)

    @staticmethod
    def _fetch_with_retries(
        fetcher: Callable[[], pd.DataFrame],
        *,
        timeout_seconds: float,
        retries: int,
        label: str,
    ) -> pd.DataFrame:
        attempts = max(1, int(retries))
        errors = []
        for _ in range(attempts):
            try:
                frame = run_with_timeout(fetcher, timeout_seconds)
                if not isinstance(frame, pd.DataFrame):
                    raise TypeError("接口未返回 DataFrame")
                return frame
            except Exception as exc:
                errors.append(_brief_error(exc))
        raise RuntimeError(f"{label}连续{attempts}次失败: {' | '.join(errors)}")

    def _failed(self, symbol: str, errors: list[str]) -> dict[str, Any]:
        return {
            "status": "source_failed",
            "symbol": symbol,
            "source": self.source_name,
            "fetched_at": utc_now_iso(),
            "events": [],
            "event_count": 0,
            "source_status": {"dividend": "failed", "rights_issue": "failed"},
            "errors": errors,
        }


def _validate_frame(frame: pd.DataFrame, required: set[str], label: str) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{label}接口未返回 DataFrame")
    if frame.empty and not set(frame.columns):
        raise ValueError(f"{label}接口返回无字段空表")
    missing = required - set(str(column) for column in frame.columns)
    if missing:
        raise ValueError(f"{label}缺少字段: {','.join(sorted(missing))}")


def _action_id(event: dict[str, Any]) -> str:
    identity = {
        "symbol": event.get("symbol"),
        "action_type": event.get("action_type"),
        "source_event_id": event.get("source_event_id"),
        "report_period": event.get("report_period"),
        "record_date": event.get("record_date"),
        "ex_date": event.get("ex_date"),
        "effective_date": event.get("effective_date"),
    }
    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:24]
    return f"ca_{digest}"


def _dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for event in events:
        action_id = str(event.get("action_id") or "")
        if action_id:
            unique[action_id] = event
    return sorted(unique.values(), key=_event_sort_key)


def _event_sort_key(event: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(event.get("effective_date") or ""),
        str(event.get("symbol") or ""),
        str(event.get("action_type") or ""),
    )


def _row_value(row: pd.Series, *names: str) -> Any:
    for name in names:
        if name in row.index:
            value = row.get(name)
            if value is not None and not (isinstance(value, float) and pd.isna(value)):
                return value
    return None


def _date_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        parsed = pd.to_datetime(value, errors="coerce")
    except Exception:
        return None
    if pd.isna(parsed):
        return None
    if isinstance(parsed, datetime):
        return parsed.date().isoformat()
    try:
        return parsed.date().isoformat()
    except Exception:
        return None


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if pd.notna(result) else None


def _text(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None
