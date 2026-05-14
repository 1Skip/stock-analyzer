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
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    if re.fullmatch(r"\d{4}/\d{2}/\d{2}", text):
        return text.replace("/", "-")
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


def _append_source(source: str | None, suffix: str) -> str:
    source = source or ""
    if suffix in source:
        return source
    return f"{source} + {suffix}" if source else suffix


def _normalize_stock_name(name: Any) -> str:
    text = re.sub(r"\s+", "", str(name or "")).replace("Ａ", "A").replace("Ｂ", "B")
    return re.sub(r"[\(（][^()（）]*(?:已切换|已退市|退市|转板)[^()（）]*[\)）]$", "", text)


def _is_missing_profile_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() in {"", "-", "--", "----", "None", "nan"}
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def _is_coarse_industry(value: Any) -> bool:
    text = str(value or "").strip()
    return re.sub(r"\s+", "", text) == "C制造业"


def _prefer_industry(current: Any, candidate: Any) -> Any:
    if _is_missing_profile_value(candidate):
        return current
    if _is_missing_profile_value(current) or _is_coarse_industry(current):
        return candidate
    if isinstance(current, str) and isinstance(candidate, str) and len(candidate.strip()) > len(current.strip()) + 2:
        return candidate
    return current


def _find_profile_index_item(index: dict[str, dict[str, Any]], symbol: str, name: str | None = None) -> dict[str, Any] | None:
    item = index.get(symbol)
    if isinstance(item, dict):
        return item

    normalized_name = _normalize_stock_name(name)
    if not normalized_name:
        return None

    for index_item in index.values():
        if not isinstance(index_item, dict):
            continue
        if _normalize_stock_name(index_item.get("name")) == normalized_name:
            return index_item
    return None


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
            return self._enrich_profile_from_full_index(profile, symbol=symbol, timeout_seconds=timeout_seconds)
        except Exception as exc:
            self.health.mark_failure(self.source_name, exc)
            logger.warning("AKShare 获取个股基础资料失败，降级到腾讯行情: symbol=%s error=%s", symbol, _brief_error(exc))
            return self._enrich_profile_from_full_index(
                self._get_stock_profile_from_tencent(symbol, timeout_seconds=2),
                symbol=symbol,
                timeout_seconds=timeout_seconds,
            )

    def get_stock_profile_index(self, timeout_seconds: float = 12) -> dict[str, dict[str, Any]]:
        """构建 A 股全量基础资料索引，用于行业/上市日期兜底。"""
        if not AKSHARE_AVAILABLE:
            return {}

        index: dict[str, dict[str, Any]] = {}
        self._merge_eastmoney_profile_index(index, timeout_seconds=timeout_seconds)
        self._merge_exchange_profile_index(index, timeout_seconds=timeout_seconds)
        return index

    def _merge_eastmoney_profile_index(self, index: dict[str, dict[str, Any]], timeout_seconds: float = 12) -> None:
        fields = "f12,f14,f20,f21,f23,f26,f38,f39,f100"
        params = {
            "pn": 1,
            "pz": 10000,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f12",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
            "fields": fields,
        }
        hosts = ["https://40.push2.eastmoney.com", "https://push2.eastmoney.com", "https://82.push2.eastmoney.com"]
        last_error: Exception | None = None
        for host in hosts:
            try:
                response = requests.get(
                    f"{host}/api/qt/clist/get",
                    params=params,
                    headers=_HTTP_HEADERS,
                    timeout=timeout_seconds,
                )
                response.raise_for_status()
                rows = ((response.json().get("data") or {}).get("diff") or [])
                for row in rows:
                    symbol = str(row.get("f12") or "").zfill(6)
                    if not re.fullmatch(r"\d{6}", symbol):
                        continue
                    item = index.setdefault(symbol, {"symbol": symbol, "market": "CN"})
                    item.update({
                        "symbol": symbol,
                        "name": str(row.get("f14") or "").replace(" ", "").strip() or item.get("name"),
                        "industry": str(row.get("f100") or "").strip() or item.get("industry"),
                        "listing_date": _format_listing_date(row.get("f26")) or item.get("listing_date"),
                        "market_cap": _safe_float(row.get("f20")) or item.get("market_cap"),
                        "float_market_cap": _safe_float(row.get("f21")) or item.get("float_market_cap"),
                        "total_shares": _safe_float(row.get("f38")) or item.get("total_shares"),
                        "float_shares": _safe_float(row.get("f39")) or item.get("float_shares"),
                        "pb": _safe_float(row.get("f23")) or item.get("pb"),
                        "source": _append_source(item.get("source"), "东方财富全量快照"),
                    })
                if rows:
                    return
            except Exception as exc:
                last_error = exc
                continue
        if last_error:
            logger.debug("东方财富全量基础资料索引失败: %s", _brief_error(last_error), exc_info=True)

    def _merge_exchange_profile_index(self, index: dict[str, dict[str, Any]], timeout_seconds: float = 12) -> None:
        tasks = [
            ("上交所主板", lambda: ak.stock_info_sh_name_code(symbol="主板A股"), self._merge_sse_profile_rows),
            ("上交所科创板", lambda: ak.stock_info_sh_name_code(symbol="科创板"), self._merge_sse_profile_rows),
            ("深交所A股", lambda: ak.stock_info_sz_name_code(symbol="A股列表"), self._merge_szse_profile_rows),
            ("北交所", lambda: ak.stock_info_bj_name_code(), self._merge_bse_profile_rows),
        ]
        per_call_timeout = max(min(timeout_seconds, 8), 3)
        for source_name, fetcher, merger in tasks:
            try:
                df = _run_with_timeout(fetcher, per_call_timeout)
                merger(index, df, source_name)
            except Exception as exc:
                logger.debug("%s 基础资料索引失败: %s", source_name, _brief_error(exc), exc_info=True)

    def _merge_sse_profile_rows(self, index: dict[str, dict[str, Any]], df: pd.DataFrame, source_name: str) -> None:
        if df is None or df.empty:
            return
        for _, row in df.iterrows():
            symbol = str(row.get("证券代码") or "").zfill(6)
            if not re.fullmatch(r"\d{6}", symbol):
                continue
            item = index.setdefault(symbol, {"symbol": symbol, "market": "CN"})
            item.update({
                "name": str(row.get("证券简称") or row.get("公司简称") or "").replace(" ", "").strip() or item.get("name"),
                "listing_date": _format_listing_date(row.get("上市日期")) or item.get("listing_date"),
                "source": _append_source(item.get("source"), source_name),
            })

    def _merge_szse_profile_rows(self, index: dict[str, dict[str, Any]], df: pd.DataFrame, source_name: str) -> None:
        if df is None or df.empty:
            return
        for _, row in df.iterrows():
            symbol = str(row.get("A股代码") or "").zfill(6)
            if not re.fullmatch(r"\d{6}", symbol):
                continue
            item = index.setdefault(symbol, {"symbol": symbol, "market": "CN"})
            item.update({
                "name": str(row.get("A股简称") or "").replace(" ", "").strip() or item.get("name"),
                "industry": str(row.get("所属行业") or "").strip() or item.get("industry"),
                "listing_date": _format_listing_date(row.get("A股上市日期")) or item.get("listing_date"),
                "total_shares": _safe_float(str(row.get("A股总股本") or "").replace(",", "")) or item.get("total_shares"),
                "float_shares": _safe_float(str(row.get("A股流通股本") or "").replace(",", "")) or item.get("float_shares"),
                "source": _append_source(item.get("source"), source_name),
            })

    def _merge_bse_profile_rows(self, index: dict[str, dict[str, Any]], df: pd.DataFrame, source_name: str) -> None:
        if df is None or df.empty:
            return
        for _, row in df.iterrows():
            symbol = str(row.get("证券代码") or "").zfill(6)
            if not re.fullmatch(r"\d{6}", symbol):
                continue
            item = index.setdefault(symbol, {"symbol": symbol, "market": "CN"})
            item.update({
                "name": str(row.get("证券简称") or "").replace(" ", "").strip() or item.get("name"),
                "industry": str(row.get("所属行业") or "").strip() or item.get("industry"),
                "listing_date": _format_listing_date(row.get("上市日期")) or item.get("listing_date"),
                "total_shares": _safe_float(row.get("总股本")) or item.get("total_shares"),
                "float_shares": _safe_float(row.get("流通股本")) or item.get("float_shares"),
                "source": _append_source(item.get("source"), source_name),
            })

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
            profile = StockProfile(
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
            return self._enrich_profile_from_cninfo(profile, timeout_seconds=timeout_seconds)
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
                return self._enrich_profile_from_cninfo(profile, timeout_seconds=timeout_seconds)
            float_market_cap = _safe_float(parts[44])
            market_cap = _safe_float(parts[45])
            enriched = StockProfile(
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
            return self._enrich_profile_from_cninfo(enriched, timeout_seconds=timeout_seconds)
        except Exception:
            logger.debug("腾讯估值补充失败 symbol=%s", profile.symbol, exc_info=True)
            return self._enrich_profile_from_cninfo(profile, timeout_seconds=timeout_seconds)

    def _enrich_profile_from_cninfo(self, profile: StockProfile | None, timeout_seconds: float = 2) -> StockProfile | None:
        """用巨潮 profile 补充行业、上市日期等腾讯快行情没有的字段。"""
        if (
            profile is None
            or (
                profile.industry
                and profile.listing_date
                and not _is_coarse_industry(profile.industry)
            )
            or not AKSHARE_AVAILABLE
        ):
            return profile
        try:
            df = _run_with_timeout(
                lambda: ak.stock_profile_cninfo(symbol=profile.symbol),
                timeout_seconds,
            )
            if df is None or df.empty:
                return profile
            row = df.iloc[0]
            industry = _prefer_industry(profile.industry, str(row.get("所属行业") or "").strip())
            listing_date = _format_listing_date(row.get("上市日期")) or profile.listing_date
            name = str(row.get("A股简称") or "").replace(" ", "").strip() or profile.name
            company_name = str(row.get("公司名称") or "").strip()
            source_suffix = " + 巨潮资讯"
            source = profile.source or ""
            if "巨潮资讯" not in source:
                source = f"{source}{source_suffix}" if source else "巨潮资讯"
            return StockProfile(
                **{
                    **profile.to_dict(),
                    "name": name,
                    "industry": industry,
                    "listing_date": listing_date,
                    "source": source,
                    "updated_at": utc_now_iso(),
                }
            )
        except Exception as exc:
            logger.debug("巨潮资料补充失败 symbol=%s error=%s", profile.symbol, _brief_error(exc), exc_info=True)
            return profile

    def _enrich_profile_from_full_index(
        self,
        profile: StockProfile | None,
        symbol: str | None = None,
        timeout_seconds: float = 5,
    ) -> StockProfile | None:
        if (
            profile is not None
            and not _is_missing_profile_value(profile.industry)
            and not _is_coarse_industry(profile.industry)
            and not _is_missing_profile_value(profile.listing_date)
        ):
            return profile
        try:
            index = self.get_stock_profile_index(timeout_seconds=max(timeout_seconds, 12))
            lookup_symbol = str(symbol or (profile.symbol if profile else "") or "").zfill(6)
            item = _find_profile_index_item(index, lookup_symbol, profile.name if profile else None)
            if not item:
                return profile
            item_name = item.get("name")
            if profile is None:
                return StockProfile(
                    symbol=lookup_symbol,
                    name=item_name,
                    market="CN",
                    industry=item.get("industry"),
                    listing_date=item.get("listing_date"),
                    total_shares=item.get("total_shares"),
                    float_shares=item.get("float_shares"),
                    market_cap=item.get("market_cap"),
                    float_market_cap=item.get("float_market_cap"),
                    pb=item.get("pb"),
                    source=_append_source(str(item.get("source") or ""), "A股全量基础资料索引"),
                    updated_at=utc_now_iso(),
                )
            source_suffix = str(item.get("source") or "A股全量基础资料索引")
            if item.get("symbol") and item.get("symbol") != profile.symbol:
                source_suffix = f"{source_suffix}(现代码{item.get('symbol')})"
            return StockProfile(
                **{
                    **profile.to_dict(),
                    "name": item_name if "已切换" in str(profile.name or "") else profile.name or item_name,
                    "industry": _prefer_industry(profile.industry, item.get("industry")),
                    "listing_date": item.get("listing_date") if _is_missing_profile_value(profile.listing_date) else profile.listing_date,
                    "total_shares": item.get("total_shares") if _is_missing_profile_value(profile.total_shares) else profile.total_shares,
                    "float_shares": item.get("float_shares") if _is_missing_profile_value(profile.float_shares) else profile.float_shares,
                    "market_cap": item.get("market_cap") if _is_missing_profile_value(profile.market_cap) else profile.market_cap,
                    "float_market_cap": item.get("float_market_cap") if _is_missing_profile_value(profile.float_market_cap) else profile.float_market_cap,
                    "pb": item.get("pb") if _is_missing_profile_value(profile.pb) else profile.pb,
                    "source": _append_source(profile.source, source_suffix),
                    "updated_at": utc_now_iso(),
                }
            )
        except Exception as exc:
            fallback_symbol = symbol or (profile.symbol if profile else "")
            logger.debug("A股全量基础资料索引补充失败 symbol=%s error=%s", fallback_symbol, _brief_error(exc), exc_info=True)
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
