"""AKShare 数据源适配器。"""
from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import requests

from data.health import SourceHealthRegistry
from data.models import StockProfile, utc_now_iso
from data.runtime import run_with_timeout

try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except Exception:
    ak = None
    AKSHARE_AVAILABLE = False


logger = logging.getLogger(__name__)
_HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
        if pd.isna(number):
            return None
        return number
    except Exception:
        return None


def _format_listing_date(value: Any) -> str | None:
    text = str(value).strip()
    if not re.fullmatch(r"\d{8}", text):
        return None
    return f"{text[:4]}-{text[4:6]}-{text[6:]}"


def _brief_error(error: Exception | str) -> str:
    text = str(error)
    host_match = re.search(r"host='([^']+)'", text)
    if host_match:
        return f"{type(error).__name__}: {host_match.group(1)} 请求失败"
    parsed = urlparse(text)
    if parsed.netloc:
        return f"{type(error).__name__}: {parsed.netloc} 请求失败"
    return text[:180]


_run_with_timeout = run_with_timeout


class AkShareProvider:
    """封装 AKShare 原始接口，向 service 返回标准模型。"""

    source_name = "AKShare/东方财富"

    def __init__(self, health: SourceHealthRegistry | None = None):
        self.health = health or SourceHealthRegistry()

    def get_stock_profile(self, symbol: str, timeout_seconds: float = 5) -> StockProfile | None:
        if not AKSHARE_AVAILABLE:
            self.health.mark_failure(self.source_name, "AKShare 不可用")
            return None
        try:
            df = _run_with_timeout(
                lambda: ak.stock_individual_info_em(symbol=symbol),
                timeout_seconds,
            )
            profile = self._normalize_stock_profile(symbol, df)
            profile = self._enrich_valuation_from_tencent(profile, timeout_seconds=2)
            self.health.mark_success(self.source_name)
            return profile
        except Exception as exc:
            self.health.mark_failure(self.source_name, exc)
            logger.warning("AKShare 获取个股基础资料失败，降级到腾讯行情: symbol=%s error=%s", symbol, _brief_error(exc))
            return self._get_stock_profile_from_tencent(symbol, timeout_seconds=2)

    def _get_stock_profile_from_tencent(self, symbol: str, timeout_seconds: float = 2) -> StockProfile | None:
        """腾讯快行情 fallback：至少保证名称、价格、估值和市值可用。"""
        prefix = "sh" if symbol.startswith("6") else "bj" if symbol.startswith(("4", "8")) else "sz"
        try:
            response = requests.get(
                f"https://qt.gtimg.cn/q={prefix}{symbol}",
                headers=_HTTP_HEADERS,
                timeout=timeout_seconds,
            )
            if response.status_code != 200:
                return None
            parts = response.text.split("~")
            if len(parts) < 47 or not parts[1]:
                return None
            total_shares = _safe_float(parts[73]) if len(parts) > 73 else None
            float_shares = _safe_float(parts[72]) if len(parts) > 72 else None
            float_market_cap = _safe_float(parts[44])
            market_cap = _safe_float(parts[45])
            return StockProfile(
                symbol=symbol,
                name=parts[1].replace(" ", "") or None,
                market="CN",
                latest_price=_safe_float(parts[3]),
                total_shares=total_shares,
                float_shares=float_shares,
                market_cap=market_cap * 1e8 if market_cap else None,
                float_market_cap=float_market_cap * 1e8 if float_market_cap else None,
                pe_ttm=_safe_float(parts[39]),
                pb=_safe_float(parts[46]),
                turnover_rate=_safe_float(parts[38]),
                source="腾讯行情",
                updated_at=utc_now_iso(),
            )
        except Exception:
            logger.warning("腾讯行情 fallback 获取基础资料失败 symbol=%s", symbol, exc_info=True)
            return None

    def _enrich_valuation_from_tencent(self, profile: StockProfile | None, timeout_seconds: float = 2) -> StockProfile | None:
        """用腾讯快行情补充 PE/PB/换手率等估值字段。"""
        if profile is None:
            return None
        prefix = "sh" if profile.symbol.startswith("6") else "bj" if profile.symbol.startswith(("4", "8")) else "sz"
        try:
            response = requests.get(
                f"https://qt.gtimg.cn/q={prefix}{profile.symbol}",
                headers=_HTTP_HEADERS,
                timeout=timeout_seconds,
            )
            if response.status_code != 200:
                return profile
            parts = response.text.split("~")
            if len(parts) < 47:
                return profile
            float_market_cap = _safe_float(parts[44])
            market_cap = _safe_float(parts[45])
            return StockProfile(
                **{
                    **profile.to_dict(),
                    "latest_price": _safe_float(parts[3]) or profile.latest_price,
                    "market_cap": market_cap * 1e8 if market_cap else profile.market_cap,
                    "float_market_cap": float_market_cap * 1e8 if float_market_cap else profile.float_market_cap,
                    "pe_ttm": _safe_float(parts[39]),
                    "pb": _safe_float(parts[46]),
                    "turnover_rate": _safe_float(parts[38]),
                    "source": f"{profile.source} + 腾讯行情",
                    "updated_at": utc_now_iso(),
                }
            )
        except Exception:
            logger.debug("腾讯估值补充失败 symbol=%s", profile.symbol, exc_info=True)
            return profile

    def _normalize_stock_profile(self, symbol: str, df: pd.DataFrame) -> StockProfile | None:
        if df is None or df.empty or "item" not in df.columns or "value" not in df.columns:
            return None
        raw = {
            str(row["item"]).strip(): row["value"]
            for _, row in df.iterrows()
            if str(row.get("item", "")).strip()
        }
        code = str(raw.get("股票代码") or symbol).strip()
        return StockProfile(
            symbol=code,
            name=str(raw.get("股票简称") or "").strip() or None,
            market="CN",
            industry=str(raw.get("行业") or "").strip() or None,
            listing_date=_format_listing_date(raw.get("上市时间")),
            latest_price=_safe_float(raw.get("最新")),
            total_shares=_safe_float(raw.get("总股本")),
            float_shares=_safe_float(raw.get("流通股")),
            market_cap=_safe_float(raw.get("总市值")),
            float_market_cap=_safe_float(raw.get("流通市值")),
            source=self.source_name,
            updated_at=utc_now_iso(),
        )
