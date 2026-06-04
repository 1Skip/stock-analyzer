"""Hot stock ranking helpers."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any


CODE = "\u4ee3\u7801"
NAME = "\u540d\u79f0"
LATEST_PRICE = "\u6700\u65b0\u4ef7"
CHANGE_PCT = "\u6da8\u8dcc\u5e45"
TURNOVER_RATE = "\u6362\u624b\u7387"
VOLUME = "\u6210\u4ea4\u91cf"
AMOUNT = "\u6210\u4ea4\u989d"
HEAT_SCORE = "\u70ed\u5ea6\u5206\u6570"


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
) -> list[dict[str, Any]]:
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
    results.sort(key=lambda item: item[HEAT_SCORE], reverse=True)
    return results[:limit]


def hot_stocks_us(
    symbols: list[str],
    *,
    yf_module: Any,
    limit: int = 20,
    max_workers: int = 5,
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
    results.sort(key=lambda item: item["volume"], reverse=True)
    return results[:limit]
