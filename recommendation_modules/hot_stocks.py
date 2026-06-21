"""Hot stock ranking helpers."""
from __future__ import annotations

import re
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests
import pandas as pd

from data.providers.sina_realtime_provider import SinaRealtimeProvider


CODE = "\u4ee3\u7801"
NAME = "\u540d\u79f0"
LATEST_PRICE = "\u6700\u65b0\u4ef7"
CHANGE_PCT = "\u6da8\u8dcc\u5e45"
TURNOVER_RATE = "\u6362\u624b\u7387"
VOLUME = "\u6210\u4ea4\u91cf"
AMOUNT = "\u6210\u4ea4\u989d"
HEAT_SCORE = "\u70ed\u5ea6\u5206\u6570"


_SINA_SESSION = requests.Session()
_SINA_SESSION.trust_env = False


def _default_sina_provider() -> SinaRealtimeProvider:
    return SinaRealtimeProvider(_SINA_SESSION)


def hot_stocks_cn(
    stocks: list[dict[str, Any]],
    *,
    requests_module: Any,
    limit: int = 20,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    headers = {
        "Referer": "https://finance.sina.com.cn",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    try:
        sh_stocks = [stock for stock in stocks if stock["code"].startswith(("600", "601", "603", "605", "688"))]
        sz_stocks = [stock for stock in stocks if stock not in sh_stocks]
        all_quotes: dict[str, list[str]] = {}

        if sh_stocks:
            codes = [f"sh{stock['code']}" for stock in sh_stocks]
            try:
                response = requests_module.get(f"https://hq.sinajs.cn/list={','.join(codes)}", headers=headers, timeout=10)
                if response.status_code == 200:
                    for line in response.text.strip().split("\n"):
                        match = re.search(r'hq_str_sh(\d+)="([^"]*)"', line)
                        if match:
                            data = match.group(2).split(",")
                            if len(data) >= 33:
                                all_quotes[match.group(1)] = data
            except Exception:
                pass

        if sz_stocks:
            codes = [f"sz{stock['code']}" for stock in sz_stocks]
            try:
                response = requests_module.get(f"https://hq.sinajs.cn/list={','.join(codes)}", headers=headers, timeout=10)
                if response.status_code == 200:
                    for line in response.text.strip().split("\n"):
                        match = re.search(r'hq_str_sz(\d+)="([^"]*)"', line)
                        if match:
                            data = match.group(2).split(",")
                            if len(data) >= 33:
                                all_quotes[match.group(1)] = data
            except Exception:
                pass

        for stock in stocks:
            code = stock["code"]
            data = all_quotes.get(code)
            if not data:
                continue
            try:
                name = data[0]
                prev_close = float(data[2])
                price = float(data[3])
                volume = int(float(data[8]))
                change = ((price - prev_close) / prev_close * 100) if prev_close > 0 else 0
                results.append(
                    {
                        CODE: code,
                        NAME: name,
                        LATEST_PRICE: round(price, 2),
                        CHANGE_PCT: round(change, 2),
                        TURNOVER_RATE: None,
                        VOLUME: volume,
                        AMOUNT: int(volume * price) if volume > 0 else 0,
                        HEAT_SCORE: round(abs(change), 2),
                    }
                )
            except (ValueError, IndexError):
                continue
    except Exception:
        pass

    results.sort(key=lambda item: item[HEAT_SCORE], reverse=True)
    return results[:limit]


def hot_stocks_hk(
    stocks: list[dict[str, Any]],
    *,
    yf_module: Any,
    limit: int = 20,
    max_workers: int = 5,
    sina_provider: Any | None = None,
    ak_module: Any | None = None,
    eastmoney_provider: Any | None | bool = None,
) -> list[dict[str, Any]]:
    ak_results = _hot_stocks_hk_from_akshare(
        ak_module,
        limit=limit,
        eastmoney_provider=eastmoney_provider,
    )
    if ak_results:
        return ak_results[:limit]

    results: list[dict[str, Any]] = []

    def fetch_stock_info(stock: dict[str, Any]) -> dict[str, Any] | None:
        try:
            symbol = stock["code"]
            ticker = yf_module.Ticker(f"{symbol}.HK")
            hist = ticker.history(period="5d")
            if hist.empty or len(hist) < 2:
                return None
            latest = hist.iloc[-1]
            prev = hist.iloc[-2]
            change = ((latest["Close"] - prev["Close"]) / prev["Close"] * 100)
            return {
                CODE: symbol,
                NAME: stock["name"],
                LATEST_PRICE: round(latest["Close"], 2),
                CHANGE_PCT: round(change, 2),
                TURNOVER_RATE: None,
                VOLUME: int(latest["Volume"]),
                AMOUNT: int(latest["Volume"] * latest["Close"]),
                HEAT_SCORE: round(abs(change), 2),
            }
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_stock_info, stock): stock for stock in stocks[:limit]}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)
    if not results:
        results = _hot_stocks_hk_from_sina(stocks[:limit], sina_provider=sina_provider)
    results.sort(key=lambda item: item[HEAT_SCORE], reverse=True)
    return results[:limit]


def hot_stocks_us(
    symbols: list[str],
    *,
    yf_module: Any,
    limit: int = 20,
    max_workers: int = 5,
    sina_provider: Any | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    def fetch_stock_info(symbol: str) -> dict[str, Any] | None:
        try:
            ticker = yf_module.Ticker(symbol)
            hist = ticker.history(period="5d")
            info = ticker.info
            if hist.empty or len(hist) < 2:
                return None
            latest = hist.iloc[-1]
            prev = hist.iloc[-2]
            change = ((latest["Close"] - prev["Close"]) / prev["Close"] * 100)
            return {
                "symbol": symbol,
                "name": info.get("shortName", symbol),
                "price": round(latest["Close"], 2),
                "change": round(change, 2),
                "volume": int(latest["Volume"]),
                "market_cap": info.get("marketCap", 0),
            }
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_stock_info, symbol): symbol for symbol in symbols[:limit]}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)
    if not results:
        results = _hot_stocks_us_from_sina(symbols[:limit], sina_provider=sina_provider)
    results.sort(key=lambda item: item["volume"], reverse=True)
    return results[:limit]


def _hot_stocks_hk_from_sina(
    stocks: list[dict[str, Any]],
    *,
    sina_provider: Any | None = None,
) -> list[dict[str, Any]]:
    provider = sina_provider or _default_sina_provider()
    results: list[dict[str, Any]] = []
    for stock in stocks:
        symbol = str(stock.get("code") or "").strip()
        if not symbol:
            continue
        try:
            quote = provider.fetch_global_quote(symbol, "hk")
        except Exception:
            quote = None
        if not quote:
            continue
        price = _safe_float(quote.get("price"))
        change = _safe_float(quote.get("change"))
        volume = _safe_float(quote.get("volume")) or 0
        if price is None or change is None:
            continue
        results.append(
            {
                CODE: symbol,
                NAME: quote.get("name") or stock.get("name") or symbol,
                LATEST_PRICE: round(price, 2),
                CHANGE_PCT: round(change, 2),
                TURNOVER_RATE: None,
                VOLUME: int(volume),
                AMOUNT: int(volume * price) if volume > 0 else 0,
                HEAT_SCORE: round(abs(change), 2),
                "source": "新浪财经",
            }
        )
    return results


def _hot_stocks_hk_from_akshare(
    ak_module: Any | None,
    *,
    limit: int,
    eastmoney_provider: Any | None | bool = None,
) -> list[dict[str, Any]]:
    if eastmoney_provider is not False:
        provider = eastmoney_provider or _hot_stocks_hk_from_eastmoney
        try:
            direct_results = provider(limit=limit)
        except TypeError:
            direct_results = provider(limit)
        if direct_results:
            return direct_results
    if ak_module is None or not hasattr(ak_module, "stock_hk_hot_rank_em"):
        return []
    try:
        df = _call_without_proxy_env(ak_module.stock_hk_hot_rank_em)
    except Exception:
        return []
    if df is None or getattr(df, "empty", True):
        return []
    results: list[dict[str, Any]] = []
    for _, row in df.head(limit).iterrows():
        symbol = str(row.get(CODE) or row.get("代码") or "").strip()
        if not symbol:
            continue
        price = _safe_float(row.get(LATEST_PRICE) or row.get("最新价"))
        change = _safe_float(row.get(CHANGE_PCT) or row.get("涨跌幅"))
        if price is None or change is None:
            continue
        results.append(
            {
                CODE: symbol.zfill(5) if symbol.isdigit() else symbol,
                NAME: row.get(NAME) or row.get("股票名称") or symbol,
                LATEST_PRICE: round(price, 2),
                CHANGE_PCT: round(change, 2),
                TURNOVER_RATE: None,
                VOLUME: None,
                AMOUNT: None,
                HEAT_SCORE: round(abs(change), 2),
                "source": "东方财富港股人气榜",
            }
        )
    return results


def _hot_stocks_hk_from_eastmoney(*, limit: int) -> list[dict[str, Any]]:
    try:
        rank_response = _SINA_SESSION.post(
            "https://emappdata.eastmoney.com/stockrank/getAllCurrHkUsList",
            json={
                "appId": "appId01",
                "globalId": "786e4c21-70dc-435a-93bb-38",
                "marketType": "000003",
                "pageNo": 1,
                "pageSize": max(100, limit),
            },
            timeout=8,
        )
        if rank_response.status_code != 200:
            return []
        rank_data = rank_response.json().get("data") or []
        rank_df = pd.DataFrame(rank_data)
        if rank_df.empty or "sc" not in rank_df.columns:
            return []
        rank_df = rank_df.head(max(1, limit)).copy()
        rank_df["code"] = rank_df["sc"].astype(str).str.split("|").str[1]
        secids = ",".join("116." + str(code) for code in rank_df["code"] if str(code))
        if not secids:
            return []
        quote_by_code = _eastmoney_hk_quotes(secids)
        if not quote_by_code:
            return _eastmoney_rank_with_sina_quotes(rank_df, limit=limit)
    except Exception:
        return []

    results: list[dict[str, Any]] = []
    for _, row in rank_df.iterrows():
        symbol = str(row.get("code") or "").strip()
        item = quote_by_code.get(symbol)
        if not symbol or not item:
            continue
        price = _safe_float(item.get("f2"))
        change = _safe_float(item.get("f3"))
        if price is None or change is None:
            continue
        results.append(
            {
                CODE: symbol.zfill(5) if symbol.isdigit() else symbol,
                NAME: item.get("f14") or symbol,
                LATEST_PRICE: round(price, 2),
                CHANGE_PCT: round(change, 2),
                TURNOVER_RATE: None,
                VOLUME: None,
                AMOUNT: None,
                HEAT_SCORE: round(abs(change), 2),
                "source": "东方财富港股人气榜",
            }
        )
    return results[:limit]


def _eastmoney_hk_quotes(secids: str) -> dict[str, dict[str, Any]]:
    try:
        quote_response = _SINA_SESSION.get(
            "https://push2.eastmoney.com/api/qt/ulist.np/get",
            params={
                "ut": "f057cbcbce2a86e2866ab8877db1d059",
                "fltt": "2",
                "invt": "2",
                "fields": "f14,f3,f12,f2",
                "secids": secids,
            },
            timeout=8,
        )
        if quote_response.status_code != 200:
            return {}
        quotes = ((quote_response.json().get("data") or {}).get("diff")) or []
        return {str(item.get("f12") or ""): item for item in quotes}
    except Exception:
        return {}


def _eastmoney_rank_with_sina_quotes(rank_df: pd.DataFrame, *, limit: int) -> list[dict[str, Any]]:
    provider = _default_sina_provider()
    results: list[dict[str, Any]] = []
    for _, row in rank_df.iterrows():
        symbol = str(row.get("code") or "").strip()
        if not symbol:
            continue
        try:
            quote = provider.fetch_global_quote(symbol, "hk")
        except Exception:
            quote = None
        if not quote:
            continue
        price = _safe_float(quote.get("price"))
        change = _safe_float(quote.get("change"))
        volume = _safe_float(quote.get("volume")) or 0
        if price is None or change is None:
            continue
        results.append(
            {
                CODE: symbol.zfill(5) if symbol.isdigit() else symbol,
                NAME: quote.get("name") or symbol,
                LATEST_PRICE: round(price, 2),
                CHANGE_PCT: round(change, 2),
                TURNOVER_RATE: None,
                VOLUME: int(volume),
                AMOUNT: int(volume * price) if volume > 0 else 0,
                HEAT_SCORE: round(abs(change), 2),
                "source": "东方财富港股人气榜+新浪行情",
            }
        )
    return results[:limit]


def _call_without_proxy_env(func: Any) -> Any:
    proxy_keys = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    )
    old_values = {key: os.environ.get(key) for key in proxy_keys}
    old_session_init = requests.sessions.Session.__init__

    def _session_init_without_env(self: requests.Session, *args: Any, **kwargs: Any) -> None:
        old_session_init(self, *args, **kwargs)
        self.trust_env = False

    try:
        for key in proxy_keys:
            os.environ.pop(key, None)
        os.environ["NO_PROXY"] = "*"
        os.environ["no_proxy"] = "*"
        requests.sessions.Session.__init__ = _session_init_without_env
        return func()
    finally:
        requests.sessions.Session.__init__ = old_session_init
        for key, value in old_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _hot_stocks_us_from_sina(
    symbols: list[str],
    *,
    sina_provider: Any | None = None,
) -> list[dict[str, Any]]:
    provider = sina_provider or _default_sina_provider()
    results: list[dict[str, Any]] = []
    for raw_symbol in symbols:
        symbol = str(raw_symbol or "").strip().upper()
        if not symbol:
            continue
        try:
            quote = provider.fetch_global_quote(symbol, "us")
        except Exception:
            quote = None
        if not quote:
            continue
        price = _safe_float(quote.get("price"))
        change = _safe_float(quote.get("change"))
        volume = _safe_float(quote.get("volume")) or 0
        if price is None or change is None:
            continue
        results.append(
            {
                "symbol": symbol,
                "name": quote.get("name") or symbol,
                "price": round(price, 2),
                "change": round(change, 2),
                "volume": int(volume),
                "market_cap": 0,
                "source": "新浪财经",
            }
        )
    return results


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
