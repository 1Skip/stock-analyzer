"""Immutable single-stock signal snapshots and later real-K settlement."""
from __future__ import annotations

from datetime import datetime
from math import sqrt
from typing import Any

import pandas as pd

from data.cache import JsonFileCache
from data.periods import period_for_start_date


ANALYSIS_SIGNAL_VERSION = "analysis_signal_v1"
ANALYSIS_SIGNAL_HORIZONS = (1, 5, 20)


class AnalysisSignalTracker:
    """Freeze analysis-time outputs and settle them against future qfq closes."""

    def __init__(self, cache: JsonFileCache | None = None, quote_service: Any | None = None):
        self.cache = cache or JsonFileCache("analysis_signal_snapshots", 86400 * 365 * 3)
        self.quote_service = quote_service

    def record_and_evaluate(
        self,
        *,
        symbol: str,
        name: str,
        market: str,
        data: pd.DataFrame,
        signals: dict[str, Any],
        quant_snapshot: dict[str, Any] | None = None,
        decision_snapshot: dict[str, Any] | None = None,
        observed_at: datetime | None = None,
    ) -> dict[str, Any]:
        record = self.record_snapshot(
            symbol=symbol,
            name=name,
            market=market,
            data=data,
            signals=signals,
            quant_snapshot=quant_snapshot,
            decision_snapshot=decision_snapshot,
            observed_at=observed_at,
        )
        if market == "CN" and data is not None and not data.empty:
            self.settle_symbol_with_frame(symbol, data)
        return {
            "record": record,
            "symbol_summary": self.summarize(symbol=symbol),
            "global_summary": self.summarize(),
            "source": "分析时冻结信号 + 后续真实1年前复权日K",
        }

    def record_snapshot(
        self,
        *,
        symbol: str,
        name: str,
        market: str,
        data: pd.DataFrame,
        signals: dict[str, Any],
        quant_snapshot: dict[str, Any] | None = None,
        decision_snapshot: dict[str, Any] | None = None,
        observed_at: datetime | None = None,
    ) -> dict[str, Any]:
        if market != "CN" or data is None or getattr(data, "empty", True):
            return {"status": "not_recorded", "reason": "当前仅记录A股真实日K信号。"}
        frame = _prepare_frame(data)
        if frame.empty:
            return {"status": "not_recorded", "reason": "日K日期或收盘价缺失。"}
        latest = frame.iloc[-1]
        data_as_of = latest["_date"].date().isoformat()
        entry_price = _number(latest.get("close"))
        if entry_price is None or entry_price <= 0:
            return {"status": "not_recorded", "reason": "日K收盘价缺失。"}
        key = f"{ANALYSIS_SIGNAL_VERSION}:{market}:{str(symbol).strip()}:{data_as_of}"
        existing = self.cache.get(key)
        if isinstance(existing, dict):
            return existing

        recommendation = str((signals or {}).get("recommendation") or "观望")
        decision_snapshot = decision_snapshot if isinstance(decision_snapshot, dict) else {}
        quant_snapshot = quant_snapshot if isinstance(quant_snapshot, dict) else {}
        record = {
            "version": ANALYSIS_SIGNAL_VERSION,
            "status": "pending",
            "recorded_at": (observed_at or datetime.now()).isoformat(timespec="seconds"),
            "symbol": str(symbol).strip(),
            "name": name or symbol,
            "market": market,
            "data_as_of": data_as_of,
            "entry_reference_price": round(entry_price, 3),
            "technical_recommendation": recommendation,
            "technical_direction": _technical_direction(recommendation),
            "decision_direction": _decision_direction(decision_snapshot),
            "decision_score": _number(decision_snapshot.get("score")),
            "decision_confidence": _number(decision_snapshot.get("confidence")),
            "decision_action": decision_snapshot.get("action"),
            "quant_score": _number(quant_snapshot.get("score")),
            "quant_version": quant_snapshot.get("version"),
            "returns": {},
            "settlement_prices": {},
            "settlement_dates": {},
            "outcomes": {"technical": {}, "decision": {}},
            "source": "single_stock_analysis_frozen_snapshot",
        }
        self.cache.set(key, record)
        return record

    def settle_symbol_with_frame(self, symbol: str, data: pd.DataFrame) -> int:
        frame = _prepare_frame(data)
        if frame.empty:
            return 0
        updates = {}
        for key, record in self._records_with_keys(symbol=symbol):
            settled = _settle_record(record, frame)
            if settled != record:
                updates[key] = settled
        if updates:
            self.cache.set_many(updates)
        return len(updates)

    def refresh_history(self, *, max_symbols: int = 50) -> dict[str, Any]:
        if self.quote_service is None:
            from data.services.quote_service import QuoteDataService

            self.quote_service = QuoteDataService()
        records = self._records_with_keys()
        pending_by_symbol: dict[str, list[dict[str, Any]]] = {}
        for _, record in records:
            if record.get("status") != "completed" and record.get("market") == "CN":
                pending_by_symbol.setdefault(str(record.get("symbol") or ""), []).append(record)
        refreshed = 0
        failed = 0
        for symbol, symbol_records in list(pending_by_symbol.items())[: max(0, int(max_symbols))]:
            if not symbol:
                continue
            oldest = min(str(item.get("data_as_of") or "") for item in symbol_records)
            period = period_for_start_date(oldest)
            try:
                frame = self.quote_service.get_stock_data(symbol, period=period, market="CN", adjust="qfq")
                refreshed += self.settle_symbol_with_frame(symbol, frame)
            except Exception:
                failed += 1
        return {
            "status": "success" if failed == 0 else "partial",
            "symbols": min(len(pending_by_symbol), max(0, int(max_symbols))),
            "updated_records": refreshed,
            "failed_symbols": failed,
            "summary": self.summarize(),
        }

    def summarize(self, *, symbol: str | None = None, limit: int = 5000) -> dict[str, Any]:
        records = [record for _, record in self._records_with_keys(symbol=symbol)][: max(1, int(limit))]
        models = {}
        for model, direction_field in (("technical", "technical_direction"), ("decision", "decision_direction")):
            rows = []
            for horizon in ANALYSIS_SIGNAL_HORIZONS:
                values = []
                successes = []
                for record in records:
                    direction = record.get(direction_field)
                    raw_return = _number((record.get("returns") or {}).get(f"{horizon}d"))
                    if direction not in {"bullish", "bearish"} or raw_return is None:
                        continue
                    directed = raw_return if direction == "bullish" else -raw_return
                    values.append(directed)
                    successes.append(directed > 0)
                wins = sum(successes)
                total = len(successes)
                ci_low, ci_high = _wilson(wins, total)
                rows.append({
                    "horizon": f"{horizon}日",
                    "sample_count": total,
                    "success_count": wins,
                    "success_rate_pct": round(wins / total * 100, 2) if total else None,
                    "success_rate_ci_low_pct": ci_low,
                    "success_rate_ci_high_pct": ci_high,
                    "avg_directional_return_pct": round(sum(values) / len(values), 2) if values else None,
                    "sample_tier": _sample_tier(total),
                })
            models[model] = rows
        return {
            "version": ANALYSIS_SIGNAL_VERSION,
            "symbol": symbol,
            "total_snapshots": len(records),
            "pending_snapshots": sum(record.get("status") != "completed" for record in records),
            "models": models,
            "score_buckets": _score_buckets(records),
        }

    def _records_with_keys(self, *, symbol: str | None = None) -> list[tuple[str, dict[str, Any]]]:
        payload = self.cache._read()
        rows = []
        for key, item in payload.items():
            value = item.get("value") if isinstance(item, dict) else None
            if not isinstance(value, dict) or value.get("version") != ANALYSIS_SIGNAL_VERSION:
                continue
            if symbol and str(value.get("symbol") or "") != str(symbol):
                continue
            rows.append((key, value))
        rows.sort(key=lambda item: str(item[1].get("recorded_at") or ""), reverse=True)
        return rows


def _settle_record(record: dict[str, Any], frame: pd.DataFrame) -> dict[str, Any]:
    data_as_of = pd.to_datetime(record.get("data_as_of"), errors="coerce")
    if pd.isna(data_as_of):
        return record
    base_rows = frame[frame["_date"] <= data_as_of]
    if base_rows.empty:
        return record
    base = base_rows.iloc[-1]
    future = frame[frame["_date"] > base["_date"]]
    updated = dict(record)
    returns = dict(record.get("returns") or {})
    prices = dict(record.get("settlement_prices") or {})
    dates = dict(record.get("settlement_dates") or {})
    outcomes = {
        "technical": dict((record.get("outcomes") or {}).get("technical") or {}),
        "decision": dict((record.get("outcomes") or {}).get("decision") or {}),
    }
    base_close = _number(base.get("close"))
    if base_close is None or base_close <= 0:
        return record
    for horizon in ANALYSIS_SIGNAL_HORIZONS:
        key = f"{horizon}d"
        if len(future) < horizon:
            continue
        target = future.iloc[horizon - 1]
        target_close = _number(target.get("close"))
        if target_close is None or target_close <= 0:
            continue
        raw_return = round((target_close / base_close - 1) * 100, 2)
        returns[key] = raw_return
        prices[key] = round(target_close, 3)
        dates[key] = target["_date"].date().isoformat()
        for model, field in (("technical", "technical_direction"), ("decision", "decision_direction")):
            direction = record.get(field)
            if direction in {"bullish", "bearish"}:
                directed = raw_return if direction == "bullish" else -raw_return
                outcomes[model][key] = {"success": directed > 0, "directional_return_pct": directed}
    if (
        returns == (record.get("returns") or {})
        and prices == (record.get("settlement_prices") or {})
        and dates == (record.get("settlement_dates") or {})
        and outcomes == (record.get("outcomes") or {})
    ):
        return record
    updated["settlement_entry_price"] = round(base_close, 3)
    updated["returns"] = returns
    updated["settlement_prices"] = prices
    updated["settlement_dates"] = dates
    updated["outcomes"] = outcomes
    updated["last_settled_at"] = datetime.now().isoformat(timespec="seconds")
    updated["status"] = "completed" if "20d" in returns else "partial" if returns else "pending"
    return updated


def _prepare_frame(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.copy()
    if "date" in frame.columns:
        frame["_date"] = pd.to_datetime(frame["date"], errors="coerce")
    else:
        frame["_date"] = pd.to_datetime(frame.index, errors="coerce")
    frame["close"] = pd.to_numeric(frame.get("close"), errors="coerce")
    return frame.dropna(subset=["_date", "close"]).sort_values("_date").reset_index(drop=True)


def _technical_direction(recommendation: str) -> str:
    if "偏多" in recommendation:
        return "bullish"
    if "偏空" in recommendation:
        return "bearish"
    return "neutral"


def _decision_direction(snapshot: dict[str, Any]) -> str:
    score = _number(snapshot.get("score"))
    if score is None:
        return "neutral"
    if score >= 62 and snapshot.get("risk_level") != "高":
        return "bullish"
    if score < 40 or snapshot.get("risk_level") == "高":
        return "bearish"
    return "neutral"


def _score_buckets(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    definitions = [(0, 49), (50, 59), (60, 69), (70, 79), (80, 100)]
    rows = []
    for low, high in definitions:
        values = []
        for record in records:
            score = _number(record.get("quant_score"))
            raw_return = _number((record.get("returns") or {}).get("5d"))
            if score is not None and raw_return is not None and low <= score <= high:
                values.append(raw_return)
        rows.append({
            "score_bucket": f"{low}-{high}",
            "sample_count": len(values),
            "up_rate_5d_pct": round(sum(value > 0 for value in values) / len(values) * 100, 2) if values else None,
            "avg_5d_return_pct": round(sum(values) / len(values), 2) if values else None,
            "sample_tier": _sample_tier(len(values)),
        })
    return rows


def _sample_tier(samples: int) -> str:
    if samples < 30:
        return "仅观察"
    if samples < 100:
        return "可参考"
    return "可横向比较"


def _wilson(wins: int, total: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if total <= 0:
        return None, None
    proportion = wins / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return round(max(0, center - margin) * 100, 2), round(min(1, center + margin) * 100, 2)


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if number == number else None
    except (TypeError, ValueError):
        return None
