"""Lightweight stock search suggestions for the Streamlit UI."""
from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher
from functools import lru_cache

from stock_names import CN_STOCK_NAMES_EXTENDED, POPULAR_US_STOCKS


_US_STOCK_NAMES = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "GOOGL": "Alphabet",
    "GOOG": "Alphabet",
    "AMZN": "Amazon",
    "TSLA": "Tesla",
    "META": "Meta Platforms",
    "NVDA": "NVIDIA",
    "NFLX": "Netflix",
    "AMD": "AMD",
    "INTC": "Intel",
    "JPM": "JPMorgan Chase",
    "V": "Visa",
    "WMT": "Walmart",
    "JNJ": "Johnson & Johnson",
    "MA": "Mastercard",
    "PG": "Procter & Gamble",
    "UNH": "UnitedHealth",
    "HD": "Home Depot",
    "BAC": "Bank of America",
    "DIS": "Disney",
}

_HK_STOCKS = {
    "00700": "腾讯控股",
    "09988": "阿里巴巴-W",
    "03690": "美团-W",
    "09618": "京东集团-SW",
    "01810": "小米集团-W",
    "01211": "比亚迪股份",
    "00941": "中国移动",
    "00883": "中国海洋石油",
    "01398": "工商银行",
    "03988": "中国银行",
    "02318": "中国平安",
    "00388": "香港交易所",
}

_CN_POPULAR_ALIASES = {
    "000001": "平安银行",
    "000002": "万科A",
    "000063": "中兴通讯",
    "000333": "美的集团",
    "000651": "格力电器",
    "000858": "五粮液",
    "002027": "分众传媒",
    "002230": "科大讯飞",
    "002415": "海康威视",
    "002594": "比亚迪",
    "300059": "东方财富",
    "300124": "汇川技术",
    "300274": "阳光电源",
    "300750": "宁德时代",
    "600000": "浦发银行",
    "600030": "中信证券",
    "600036": "招商银行",
    "600276": "恒瑞医药",
    "600309": "万华化学",
    "600519": "贵州茅台",
    "600690": "海尔智家",
    "600900": "长江电力",
    "601012": "隆基绿能",
    "601318": "中国平安",
    "601398": "工商银行",
    "601668": "中国建筑",
    "601888": "中国中免",
    "601899": "紫金矿业",
    "603259": "药明康德",
    "603288": "海天味业",
    "688981": "中芯国际",
}

_CN_QUERY_ALIASES = {
    "瑞鸽": "瑞鹄",
}


def _normalize_query(value: str) -> str:
    normalized = re.sub(r"\s+", "", str(value or "")).upper()
    return _CN_QUERY_ALIASES.get(normalized, normalized)


def _query_similarity(query: str, candidate: str) -> float:
    """Return fuzzy similarity, boosting same-character transposition typos."""
    normalized = _normalize_query(query)
    normalized_candidate = _normalize_query(candidate)
    if not normalized or not normalized_candidate:
        return 0.0
    similarity = SequenceMatcher(None, normalized, normalized_candidate).ratio()
    if len(normalized) >= 3 and len(normalized_candidate) >= 3 and sorted(normalized) == sorted(normalized_candidate):
        similarity = max(similarity, 0.95)
    return similarity


def _is_same_char_transposition(query: str, candidate: str) -> bool:
    normalized = _normalize_query(query)
    normalized_candidate = _normalize_query(candidate)
    return (
        len(normalized) >= 3
        and len(normalized) == len(normalized_candidate)
        and normalized != normalized_candidate
        and sorted(normalized) == sorted(normalized_candidate)
    )


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(__file__))


def _load_cached_stock_index() -> list[dict[str, str]]:
    candidates = [
        os.path.join(_project_root(), ".cache", "stock_name_index.json"),
        os.path.join(_project_root(), "data", "stock_name_index.json"),
    ]
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as file:
                payload = json.load(file)
            stocks = payload.get("stocks", [])
            if isinstance(stocks, list):
                return [
                    {"code": str(item.get("code", "")).strip(), "name": str(item.get("name", "")).strip()}
                    for item in stocks
                    if item.get("code") and item.get("name")
                ]
        except Exception:
            continue
    return []


@lru_cache(maxsize=1)
def _cn_stock_pool() -> tuple[tuple[str, str], ...]:
    seen = set()
    stocks: list[tuple[str, str]] = []
    for code, name in _CN_POPULAR_ALIASES.items():
        stocks.append((code, name))
        seen.add(code)
    for code, name in CN_STOCK_NAMES_EXTENDED.items():
        if code not in seen:
            stocks.append((str(code), str(name)))
            seen.add(code)
    for item in _load_cached_stock_index():
        code = item["code"]
        if code not in seen:
            stocks.append((code, item["name"]))
            seen.add(code)
    return tuple(stocks)


def _market_pool(market: str) -> list[tuple[str, str]]:
    if market == "CN":
        return list(_cn_stock_pool())
    if market == "HK":
        return list(_HK_STOCKS.items())
    return [(symbol, _US_STOCK_NAMES.get(symbol, symbol)) for symbol in POPULAR_US_STOCKS]


def suggest_stock_inputs(query: str, market: str = "CN", limit: int = 8) -> list[dict[str, str]]:
    """Return ranked local suggestions without touching slow remote data sources."""
    normalized = _normalize_query(query)
    pool = _market_pool(market)

    if not normalized:
        matches = pool[:limit]
    else:
        scored: list[tuple[int, int, str, str]] = []
        for code, name in pool:
            normalized_code = _normalize_query(code)
            normalized_name = _normalize_query(name)
            if normalized_code == normalized:
                score = 0
            elif normalized_name == normalized:
                score = 1
            elif _is_same_char_transposition(normalized, normalized_name):
                score = 2
            elif normalized_code.startswith(normalized):
                score = 3
            elif normalized_name.startswith(normalized):
                score = 4
            elif normalized in normalized_name:
                score = 5
            elif normalized in normalized_code:
                score = 6
            else:
                continue
            scored.append((score, len(name), code, name))

        if not scored and market == "CN" and len(normalized) >= 2:
            for code, name in pool:
                normalized_name = _normalize_query(name)
                if not normalized_name:
                    continue
                similarity = _query_similarity(normalized, normalized_name)
                if similarity >= 0.72 or (normalized_name.startswith(normalized[:1]) and similarity >= 0.30):
                    score = 7 if similarity >= 0.72 else 8
                    scored.append((score, len(name), code, name))

        matches = [(code, name) for _, _, code, name in sorted(scored)[:limit]]

    return [
        {
            "symbol": code,
            "name": name,
            "label": f"{code} · {name}",
        }
        for code, name in matches
    ]


def parse_suggestion_label(label: str) -> tuple[str, str] | None:
    if not label or " · " not in label:
        return None
    code, name = label.split(" · ", 1)
    code = code.strip()
    name = name.strip()
    if not code:
        return None
    return code, name
