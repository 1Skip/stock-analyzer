"""Baostock historical security-status and daily-bar provider."""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable

import pandas as pd


class BaostockProviderError(RuntimeError):
    """Raised when Baostock cannot return verified real data."""


class BaostockStatusProvider:
    """Use one sequential Baostock session for historical A-share queries."""

    source = "Baostock证券宝"

    def __init__(
        self,
        bs_module: Any | None = None,
        *,
        timeout_seconds: float = 15,
    ) -> None:
        self._bs = bs_module
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.connected = False

    @property
    def bs(self) -> Any:
        if self._bs is None:
            try:
                import baostock as bs
            except ImportError as exc:
                raise BaostockProviderError(
                    "未安装 baostock，不能获取逐日历史证券状态"
                ) from exc
            self._bs = bs
        return self._bs

    def __enter__(self) -> "BaostockStatusProvider":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def connect(self) -> None:
        if self.connected:
            return
        try:
            result = self.bs.login()
        except Exception as exc:
            raise BaostockProviderError(f"Baostock 登录异常: {exc}") from exc
        self._raise_for_result(result, "Baostock 登录")
        self.connected = True
        self._set_socket_timeout()

    def close(self) -> None:
        if not self.connected:
            return
        try:
            self.bs.logout()
        finally:
            self.connected = False

    def reconnect(self) -> None:
        self.close()
        self.connect()

    def query_trade_dates(self, start_date: str, end_date: str) -> list[str]:
        """Return real exchange trading dates in the requested range."""
        start, end = _date_range(start_date, end_date)
        self._require_connection()
        try:
            result = self.bs.query_trade_dates(start_date=start, end_date=end)
            rows = list(self._result_rows(result, "交易日历"))
        except BaostockProviderError:
            raise
        except Exception as exc:
            raise BaostockProviderError(f"Baostock 交易日历查询异常: {exc}") from exc

        dates = []
        for row in rows:
            flag = str(row.get("is_trading_day") or "").strip()
            if flag not in {"0", "1"}:
                raise BaostockProviderError(
                    f"Baostock 交易日历返回无法识别的 is_trading_day={flag!r}"
                )
            calendar_date = _date_text(row.get("calendar_date"))
            if flag == "1" and calendar_date:
                dates.append(calendar_date)
        return sorted(set(dates))

    def query_daily_status(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        """Return daily trading/ST flags without inventing missing dates."""
        start, end = _date_range(start_date, end_date)
        code = to_baostock_code(symbol)
        rows = self._query_history(
            code,
            "date,tradestatus,isST",
            start_date=start,
            end_date=end,
            adjustflag="3",
            purpose=f"{symbol}逐日状态",
        )
        normalized = []
        for row in rows:
            row_date = _date_text(row.get("date"))
            trade_status = str(row.get("tradestatus") or "").strip()
            is_st = str(row.get("isST") or "").strip()
            if not row_date:
                raise BaostockProviderError(f"{symbol}逐日状态缺少有效日期")
            if trade_status not in {"0", "1"}:
                raise BaostockProviderError(
                    f"{symbol}在{row_date}的 tradestatus 无法识别: {trade_status!r}"
                )
            if is_st not in {"0", "1"}:
                raise BaostockProviderError(
                    f"{symbol}在{row_date}的 isST 无法识别: {is_st!r}"
                )
            normalized.append(
                {
                    "date": row_date,
                    "trade_status": int(trade_status),
                    "is_st": is_st == "1",
                }
            )
        return normalized

    def query_daily_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Return real forward-adjusted daily bars for research-cache gaps."""
        start, end = _date_range(start_date, end_date)
        code = to_baostock_code(symbol)
        rows = self._query_history(
            code,
            "date,open,high,low,close,volume,amount,turn,tradestatus,isST",
            start_date=start,
            end_date=end,
            adjustflag="2",
            purpose=f"{symbol}前复权日K",
        )
        if not rows:
            return pd.DataFrame()

        frame = pd.DataFrame(rows)
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame["tradestatus"] = pd.to_numeric(frame["tradestatus"], errors="coerce")
        frame = frame[(frame["date"].notna()) & (frame["tradestatus"] == 1)].copy()
        frame = frame.rename(columns={"turn": "turnover", "isST": "is_st"})
        numeric_columns = ["open", "high", "low", "close", "volume", "amount", "turnover"]
        for column in numeric_columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame["turnover"] = frame["turnover"] / 100
        frame = frame.dropna(subset=["open", "high", "low", "close"])
        if frame.empty:
            return frame
        frame = frame.set_index("date").sort_index()
        frame["is_st"] = frame["is_st"].astype(str).str.strip().eq("1")
        frame = frame[
            ["open", "high", "low", "close", "volume", "amount", "turnover", "is_st"]
        ]
        frame.attrs["data_source"] = self.source
        frame.attrs["adjust_method"] = "前复权"
        frame.attrs["volume_unit"] = "share"
        return frame

    def _query_history(
        self,
        code: str,
        fields: str,
        *,
        start_date: str,
        end_date: str,
        adjustflag: str,
        purpose: str,
    ) -> list[dict[str, str]]:
        self._require_connection()
        try:
            result = self.bs.query_history_k_data_plus(
                code,
                fields,
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag=adjustflag,
            )
            return list(self._result_rows(result, purpose))
        except BaostockProviderError:
            raise
        except Exception as exc:
            raise BaostockProviderError(f"Baostock {purpose}查询异常: {exc}") from exc

    def _result_rows(
        self,
        result: Any,
        purpose: str,
    ) -> Iterable[dict[str, str]]:
        self._raise_for_result(result, f"Baostock {purpose}查询")
        fields = [str(field) for field in getattr(result, "fields", [])]
        if not fields:
            raise BaostockProviderError(f"Baostock {purpose}查询未返回字段定义")
        try:
            while result.next():
                values = list(result.get_row_data())
                if len(values) != len(fields):
                    raise BaostockProviderError(
                        f"Baostock {purpose}查询字段数与数据列数不一致"
                    )
                yield dict(zip(fields, values))
        except BaostockProviderError:
            raise
        except Exception as exc:
            raise BaostockProviderError(f"Baostock {purpose}结果读取异常: {exc}") from exc

    def _set_socket_timeout(self) -> None:
        context = getattr(getattr(self.bs, "common", None), "context", None)
        default_socket = getattr(context, "default_socket", None)
        settimeout = getattr(default_socket, "settimeout", None)
        if callable(settimeout):
            settimeout(self.timeout_seconds)

    def _require_connection(self) -> None:
        if not self.connected:
            raise BaostockProviderError("Baostock 尚未登录")

    @staticmethod
    def _raise_for_result(result: Any, purpose: str) -> None:
        error_code = str(getattr(result, "error_code", "") or "")
        if error_code != "0":
            error_message = str(getattr(result, "error_msg", "") or "未知错误")
            raise BaostockProviderError(
                f"{purpose}失败: error_code={error_code or '--'} error_msg={error_message}"
            )


def to_baostock_code(symbol: str) -> str:
    """Convert a six-digit Shanghai/Shenzhen symbol to Baostock format."""
    text = str(symbol or "").strip().lower()
    if text.startswith(("sh.", "sz.")):
        exchange, code = text.split(".", 1)
        if len(code) == 6 and code.isdigit():
            return f"{exchange}.{code}"
        raise ValueError(f"无效股票代码: {symbol!r}")
    if len(text) != 6 or not text.isdigit():
        raise ValueError(f"无效股票代码: {symbol!r}")
    if text.startswith("6"):
        return f"sh.{text}"
    if text.startswith(("0", "3")):
        return f"sz.{text}"
    raise ValueError(f"Baostock 暂不支持该市场代码: {symbol!r}")


def _date_range(start_date: Any, end_date: Any) -> tuple[str, str]:
    start = _date_text(start_date)
    end = _date_text(end_date)
    if not start or not end:
        raise ValueError(f"无效日期范围: {start_date!r} 至 {end_date!r}")
    if start > end:
        raise ValueError(f"开始日期不能晚于结束日期: {start} > {end}")
    return start, end


def _date_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except (TypeError, ValueError):
        return None
