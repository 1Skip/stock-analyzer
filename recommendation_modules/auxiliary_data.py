"""Auxiliary market data helpers used by recommendation orchestration."""
from __future__ import annotations

from typing import Any, Callable


def fetch_tencent_market_cap(
    symbol: str,
    *,
    requests_module: Any,
    safe_float: Callable[[Any], float | None],
    timeout_seconds: int = 2,
) -> tuple[float | None, str | None, str]:
    prefix = "sh" if str(symbol).startswith("6") else "bj" if str(symbol).startswith(("4", "8")) else "sz"
    try:
        response = requests_module.get(
            f"https://qt.gtimg.cn/q={prefix}{symbol}",
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://stockapp.finance.qq.com/"},
            timeout=timeout_seconds,
        )
        if response.status_code != 200:
            return None, None, "\u817e\u8baf\u884c\u60c5\u72b6\u6001\u5f02\u5e38"
        parts = response.text.split("~")
        if len(parts) < 46:
            return None, None, "\u817e\u8baf\u884c\u60c5\u5b57\u6bb5\u4e0d\u8db3"
        market_cap = safe_float(parts[45])
        name = str(parts[1] or "").replace(" ", "").strip() if len(parts) > 1 else None
        if market_cap is None or market_cap <= 0:
            return None, name, "\u817e\u8baf\u884c\u60c5\u65e0\u5e02\u503c"
        return market_cap * 1e8, name, "\u817e\u8baf\u884c\u60c5"
    except Exception as exc:
        return None, None, f"\u817e\u8baf\u884c\u60c5\u5931\u8d25: {exc}"


def stock_sector(
    code: str,
    *,
    cache: dict[str, str],
    requests_module: Any,
) -> str:
    if code in cache:
        return cache[code]
    try:
        if code.startswith(("8", "9")):
            market = "BJ"
        elif code.startswith("6"):
            market = "SH"
        else:
            market = "SZ"
        response = requests_module.get(
            "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax",
            params={"code": f"{market}{code}"},
            headers={
                "Referer": "https://emweb.securities.eastmoney.com/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
            timeout=5,
        )
        if response.status_code == 200:
            data = response.json()
            profile = data.get("jbzl") or {}
            sector = (profile.get("sshy") or "").strip()
            if sector and sector != "--":
                cache[code] = sector
                return sector
    except Exception:
        pass

    if code.startswith(("8", "9")):
        fallback = "\u5317\u4ea4\u6240"
    elif code.startswith("68"):
        fallback = "\u79d1\u521b\u677f"
    elif code.startswith(("300", "301")):
        fallback = "\u521b\u4e1a\u677f"
    elif code.startswith("6"):
        fallback = "\u6caa\u5e02\u4e3b\u677f"
    else:
        fallback = "\u6df1\u5e02\u4e3b\u677f"
    cache[code] = fallback
    return fallback
