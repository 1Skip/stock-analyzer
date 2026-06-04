"""Sina realtime quote provider."""
from __future__ import annotations

import re
from typing import Any


HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


class SinaRealtimeProvider:
    """Fetch and parse realtime quotes from Sina Finance."""

    def __init__(self, session: Any):
        self.session = session

    @staticmethod
    def cn_code(symbol: str) -> str:
        symbol = str(symbol)
        if symbol.startswith("6"):
            prefix = "sh"
        elif symbol.startswith(("4", "8")):
            prefix = "bj"
        else:
            prefix = "sz"
        return f"{prefix}{symbol}"

    @staticmethod
    def global_code(symbol: str, market: str) -> str | None:
        market = str(market or "").lower()
        if market == "hk":
            return f"hk{symbol}"
        if market == "us":
            return f"gb_{str(symbol).lower()}"
        return None

    @staticmethod
    def parse_cn_quote(symbol: str, raw: str, *, include_quote_time: bool = False) -> dict[str, Any] | None:
        if not raw:
            return None
        try:
            data = raw.split(",")
            if len(data) < 33 or not data[3]:
                return None
            price = float(data[3])
            prev_close = float(data[2])
            quote = {
                "symbol": symbol,
                "name": data[0],
                "price": price,
                "open": float(data[1]),
                "high": float(data[4]),
                "low": float(data[5]),
                "volume": float(data[8]) / 100,
                "volume_unit": "hand",
                "prev_close": prev_close,
                "change": (price / prev_close - 1) * 100 if prev_close else 0,
            }
            if include_quote_time:
                quote["quote_date"] = data[30] if len(data) > 30 else None
                quote["quote_time"] = data[31] if len(data) > 31 else None
                quote["turnover_rate"] = None
            return quote
        except (TypeError, ValueError, ZeroDivisionError):
            return None

    @staticmethod
    def parse_global_quote(symbol: str, raw: str, market: str) -> dict[str, Any] | None:
        data = raw.split(",") if raw else []
        market = str(market or "").lower()
        try:
            if market == "hk" and len(data) >= 17:
                return {
                    "symbol": symbol,
                    "name": data[1] if data[1] else data[0],
                    "price": float(data[4]),
                    "open": float(data[3]),
                    "high": float(data[2]),
                    "low": float(data[6]),
                    "volume": int(float(data[12])),
                    "prev_close": float(data[5]),
                    "change": float(data[8]),
                }
            if market == "us" and len(data) >= 11:
                return {
                    "symbol": symbol,
                    "name": data[0],
                    "price": float(data[1]),
                    "open": float(data[5]),
                    "high": float(data[6]),
                    "low": float(data[7]),
                    "volume": int(float(data[10])),
                    "prev_close": float(data[1]) - float(data[4]),
                    "change": float(data[2]),
                }
        except (TypeError, ValueError):
            return None
        return None

    def fetch_cn_quote(self, symbol: str) -> dict[str, Any] | None:
        url = f"https://hq.sinajs.cn/list={self.cn_code(symbol)}"
        response = self.session.get(url, headers=HEADERS, timeout=5)
        if response.status_code != 200:
            return None
        match = re.search(r'"([^"]*)"', response.text)
        return self.parse_cn_quote(symbol, match.group(1) if match else "", include_quote_time=True)

    def fetch_cn_name(self, symbol: str) -> str | None:
        codes = [self.cn_code(symbol)]
        if not str(symbol).startswith(("0", "3", "4", "6", "8")):
            codes.extend([f"sz{symbol}", f"sh{symbol}"])
        for code in dict.fromkeys(codes):
            try:
                response = self.session.get(f"https://hq.sinajs.cn/list={code}", headers=HEADERS, timeout=3)
                if response.status_code != 200:
                    continue
                match = re.search(r'"([^"]*)"', response.text)
                data = match.group(1).split(",") if match else []
                if data and data[0]:
                    return data[0]
            except Exception:
                continue
        return None

    def fetch_cn_batch_quotes(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        if not symbols:
            return {}
        code_to_symbol = {self.cn_code(symbol): symbol for symbol in symbols}
        url = "https://hq.sinajs.cn/list=" + ",".join(code_to_symbol.keys())
        response = self.session.get(url, headers=HEADERS, timeout=5)
        if response.status_code != 200:
            return {}
        result: dict[str, dict[str, Any]] = {}
        for code, raw in re.findall(r'var hq_str_([a-z]{2}\d{6})="([^"]*)"', response.text):
            symbol = code_to_symbol.get(code)
            parsed = self.parse_cn_quote(symbol, raw) if symbol else None
            if parsed:
                parsed["change_pct"] = round(float(parsed.get("change") or 0), 2)
                result[symbol] = parsed
        return result

    def fetch_global_quote(self, symbol: str, market: str) -> dict[str, Any] | None:
        code = self.global_code(symbol, market)
        if not code:
            return None
        response = self.session.get(f"https://hq.sinajs.cn/list={code}", headers=HEADERS, timeout=5)
        if response.status_code != 200:
            return None
        match = re.search(r'"([^"]*)"', response.text)
        return self.parse_global_quote(symbol, match.group(1) if match else "", market)
