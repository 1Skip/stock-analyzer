"""缓存数据获取层 — Streamlit @st.cache_data 封装"""
import logging
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
from config import (
    CACHE_TTL_FUNDAMENTALS,
    CACHE_TTL_INTRADAY,
    CACHE_TTL_REALTIME,
    CACHE_TTL_STOCK_DATA,
    CACHE_TTL_STOCK_EXTENDED_INFO,
    CACHE_TTL_STOCK_INFO,
)
from data.services.fundamental_service import FundamentalDataService
from data.services.info_service import StockInfoService
from data.services.quote_service import QuoteDataService


quote_service = QuoteDataService()
fetcher = quote_service.provider.fetcher
fundamental_service = FundamentalDataService()
stock_info_service = StockInfoService()
logger = logging.getLogger(__name__)
STOCK_INPUT_CACHE_VERSION = "stock-input-v4-ths-daily-kline-name-index"
STOCK_DATA_CACHE_VERSION = "stock-data-v2-ths-daily-kline"


@st.cache_data(ttl=CACHE_TTL_STOCK_DATA, max_entries=64, show_spinner=False)
def get_cached_stock_data(symbol, period, market, adjust="", cache_version=STOCK_DATA_CACHE_VERSION):
    """缓存股票数据获取"""
    try:
        return quote_service.get_stock_data(symbol, period=period, market=market, adjust=adjust)
    except Exception:
        logger.warning("缓存层获取股票数据失败: symbol=%s market=%s period=%s", symbol, market, period, exc_info=True)
        return None


def stock_data_cache_version(market="CN"):
    if market == "CN":
        return f"{STOCK_DATA_CACHE_VERSION}-{datetime.now().strftime('%Y%m%d%H%M')}"
    return STOCK_DATA_CACHE_VERSION


@st.cache_data(ttl=CACHE_TTL_STOCK_DATA, max_entries=16, show_spinner=False)
def get_cached_benchmark_data(symbol="000300", period="1y"):
    """缓存A股基准指数K线，用于 Beta 等真实相对风险指标。"""
    try:
        import akshare as ak

        period_days = {"1wk": 7, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730}
        days = period_days.get(period, 365)
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        df = None
        try:
            df = ak.index_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date)
        except Exception:
            logger.info("东财指数历史接口失败，改用新浪指数历史: symbol=%s", symbol, exc_info=True)
        if df is None or df.empty:
            sina_symbol = f"sh{symbol}" if str(symbol).startswith("000") else f"sz{symbol}"
            df = ak.stock_zh_index_daily(symbol=sina_symbol)
            if df is not None and not df.empty and "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"], errors="coerce")
                start_ts = pd.to_datetime(start_date)
                end_ts = pd.to_datetime(end_date)
                df = df[(df["date"] >= start_ts) & (df["date"] <= end_ts)]
        if df is None or df.empty:
            return None
        rename_map = {
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
        }
        df = df.rename(columns=rename_map)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df = df.dropna(subset=["date"]).set_index("date")
        for column in ["open", "high", "low", "close", "volume", "amount"]:
            if column in df.columns:
                df[column] = pd.to_numeric(df[column], errors="coerce")
        df.attrs["data_source"] = "AKShare指数历史行情"
        return df
    except Exception:
        logger.warning("缓存层获取基准指数失败: symbol=%s period=%s", symbol, period, exc_info=True)
        return None


@st.cache_data(ttl=CACHE_TTL_STOCK_INFO, max_entries=128, show_spinner=False)
def resolve_cached_stock_input(text, market, cache_version=STOCK_INPUT_CACHE_VERSION):
    """缓存股票输入解析，避免中文名称搜索重复拉全市场快照"""
    try:
        return fetcher.resolve_stock_input(text, market)
    except Exception:
        logger.warning("缓存层解析股票输入失败: text=%s market=%s", text, market, exc_info=True)
        return None


@st.cache_data(ttl=CACHE_TTL_STOCK_INFO, max_entries=128, show_spinner=False)
def get_cached_stock_info(symbol, market):
    """缓存股票基本信息"""
    try:
        return fetcher.get_stock_info(symbol, market)
    except Exception:
        logger.warning("缓存层获取股票信息失败: symbol=%s market=%s", symbol, market, exc_info=True)
        return {}


@st.cache_data(ttl=CACHE_TTL_FUNDAMENTALS, max_entries=256, show_spinner=False)
def get_cached_stock_profile(symbol, market):
    """缓存分层数据服务返回的个股基础资料。"""
    try:
        return fundamental_service.get_stock_profile(symbol, market)
    except Exception:
        logger.warning("缓存层获取个股基础资料失败: symbol=%s market=%s", symbol, market, exc_info=True)
        return None


@st.cache_data(ttl=CACHE_TTL_STOCK_EXTENDED_INFO, max_entries=128, show_spinner=False)
def get_cached_stock_extended_info(symbol, market):
    """缓存财务摘要/资金流/新闻等扩展信息。"""
    try:
        return stock_info_service.get_stock_extended_info(symbol, market, include_deep_layers=False)
    except Exception:
        logger.warning("缓存层获取个股扩展信息失败: symbol=%s market=%s", symbol, market, exc_info=True)
        return None


@st.cache_data(ttl=CACHE_TTL_REALTIME, max_entries=64, show_spinner=False)
def get_cached_realtime_quote(symbol, market):
    """缓存实时行情"""
    try:
        return quote_service.get_realtime_quote(symbol, market)
    except Exception:
        logger.warning("缓存层获取实时行情失败: symbol=%s market=%s", symbol, market, exc_info=True)
        return None


@st.cache_data(ttl=CACHE_TTL_INTRADAY, show_spinner=False)
def get_cached_intraday_data(symbol, market):
    """缓存分时数据 — 60秒缓存，仅A股"""
    try:
        return quote_service.get_intraday_data(symbol, market)
    except Exception:
        logger.warning("缓存层获取分时数据失败: symbol=%s market=%s", symbol, market, exc_info=True)
        return None
