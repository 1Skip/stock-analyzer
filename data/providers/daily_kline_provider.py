"""Daily K-line providers for legacy StockDataFetcher entrypoints."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import requests


HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

PERIOD_DAYS = {"1wk": 7, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730}


def _days(period: str) -> int:
    return PERIOD_DAYS.get(period, 365)


def _numeric_ohlcv(df: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    columns = columns or ["open", "high", "low", "close", "volume"]
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["open", "high", "low", "close"])


def _exchange_prefix(symbol: str) -> str:
    if str(symbol).startswith(("600", "601", "603", "605", "688")):
        return "sh"
    return "sz"


class ThsDailyKlineProvider:
    """Fetch A-share daily K-line from THS web endpoint."""

    source = "\u540c\u82b1\u987a"

    def __init__(self, session: Any):
        self.session = session

    def fetch(self, symbol: str, period: str, *, adjust: str = "") -> pd.DataFrame | None:
        line_code = "01" if adjust == "qfq" else "00"
        url = f"https://d.10jqka.com.cn/v6/line/hs_{symbol}/{line_code}/last.js"
        headers = {
            "Referer": f"https://stockpage.10jqka.com.cn/{symbol}/",
            "User-Agent": HEADERS["User-Agent"],
        }
        response = self.session.get(url, headers=headers, timeout=10)
        if response.status_code != 200 or not response.text.strip():
            return None

        text = response.text.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            return None
        payload = json.loads(text[start : end + 1])

        rows = []
        for item in str(payload.get("data") or "").split(";"):
            fields = item.split(",")
            if len(fields) < 6:
                continue
            rows.append(
                {
                    "date": fields[0],
                    "open": fields[1],
                    "high": fields[2],
                    "low": fields[3],
                    "close": fields[4],
                    "volume": fields[5],
                    "amount": fields[6] if len(fields) > 6 else None,
                    "turnover_rate": fields[7] if len(fields) > 7 else None,
                }
            )
        if len(rows) < 10:
            return None

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
        df.set_index("date", inplace=True)
        df = _numeric_ohlcv(df, ["open", "high", "low", "close", "volume", "amount", "turnover_rate"])
        cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=_days(period))
        df = df[df.index >= cutoff]
        if len(df) < 10:
            return None
        df.attrs["adjust_method"] = "\u524d\u590d\u6743" if adjust == "qfq" else "\u4e0d\u590d\u6743"
        df.attrs["data_provider"] = self.source
        df.attrs["volume_unit"] = "share"
        return df


class AkshareDailyKlineProvider:
    """Fetch A-share daily K-line through AKShare backed sources."""

    eastmoney_source = "\u4e1c\u65b9\u8d22\u5bcc"
    tencent_source = "\u817e\u8baf\u8d22\u7ecf"

    def __init__(self, ak_module: Any):
        self.ak = ak_module

    def fetch_eastmoney(self, symbol: str, period: str, *, adjust: str = "") -> pd.DataFrame | None:
        if self.ak is None:
            return None
        days = _days(period)
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        df = self.ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
        )
        if df is None or getattr(df, "empty", True) or len(df) < 10:
            return None
        df = df.rename(
            columns={
                "\u65e5\u671f": "date",
                "\u5f00\u76d8": "open",
                "\u6536\u76d8": "close",
                "\u6700\u9ad8": "high",
                "\u6700\u4f4e": "low",
                "\u6210\u4ea4\u91cf": "volume",
            }
        )
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        df = _numeric_ohlcv(df)
        if len(df) < 10:
            return None
        df.attrs["adjust_method"] = "\u524d\u590d\u6743" if adjust == "qfq" else "\u4e0d\u590d\u6743"
        df.attrs["data_provider"] = self.eastmoney_source
        df.attrs["volume_unit"] = "hand"
        return df

    def fetch_tencent(self, symbol: str, period: str, *, adjust: str = "") -> pd.DataFrame | None:
        if self.ak is None:
            return None
        days = _days(period)
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        df = self.ak.stock_zh_a_daily(
            symbol=f"{_exchange_prefix(symbol)}{symbol}",
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
        )
        if df is None or getattr(df, "empty", True) or len(df) < 10:
            return None
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        df = _numeric_ohlcv(df)
        if len(df) < 10:
            return None
        df.attrs["adjust_method"] = "\u524d\u590d\u6743" if adjust == "qfq" else "\u4e0d\u590d\u6743"
        df.attrs["data_provider"] = self.tencent_source
        df.attrs["volume_unit"] = "share"
        return df


class SinaDailyKlineProvider:
    """Fetch Sina daily K-lines for A-share and US stocks."""

    source = "\u65b0\u6d6a\u8d22\u7ecf"

    def __init__(self, session: Any):
        self.session = session

    def fetch_cn(self, symbol: str, period: str) -> pd.DataFrame | None:
        sina_symbol = f"{_exchange_prefix(symbol)}{symbol}"
        url = (
            "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            f"CN_MarketData.getKLineData?symbol={sina_symbol}&scale=240&ma=5&datalen={_days(period)}"
        )
        response = self.session.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200 or not response.text.strip():
            return None
        data = json.loads(response.text)
        if not data or not isinstance(data, list) or len(data) < 10:
            return None
        df = pd.DataFrame(data)
        df.rename(
            columns={"day": "date", "open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"},
            inplace=True,
        )
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        df = _numeric_ohlcv(df)
        if len(df) < 10:
            return None
        df.attrs["adjust_method"] = "\u672a\u590d\u6743\uff08\u65b0\u6d6a\u8d22\u7ecf\uff09"
        df.attrs["data_provider"] = self.source
        df.attrs["volume_unit"] = "share"
        return df

    def fetch_us(self, symbol: str, period: str) -> pd.DataFrame | None:
        datalen = max(int(_days(period) * 252 / 365) + 10, 10)
        url = "https://stock.finance.sina.com.cn/usstock/api/json_v2.php/US_MinKService.getDailyK"
        params = {"symbol": symbol.lower(), "type": "day", "datalen": datalen}
        response = self.session.get(url, params=params, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            return None
        data = response.json()
        if not data or not isinstance(data, list) or len(data) < 10:
            return None
        df = pd.DataFrame(data)
        df = df.rename(columns={"d": "date", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        df = _numeric_ohlcv(df)
        return df if len(df) >= 10 else None


def is_timeout_error(exc: Exception) -> bool:
    return isinstance(exc, requests.exceptions.Timeout)


def is_request_error(exc: Exception) -> bool:
    return isinstance(exc, requests.exceptions.RequestException)
