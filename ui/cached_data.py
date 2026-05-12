"""缓存数据获取层 — Streamlit @st.cache_data 封装"""
import logging

import streamlit as st
from data_fetcher import StockDataFetcher
from config import (
    CACHE_TTL_FUNDAMENTALS,
    CACHE_TTL_INTRADAY,
    CACHE_TTL_REALTIME,
    CACHE_TTL_STOCK_DATA,
    CACHE_TTL_STOCK_INFO,
)
from data.services.fundamental_service import FundamentalDataService


fetcher = StockDataFetcher()
fundamental_service = FundamentalDataService()
logger = logging.getLogger(__name__)
STOCK_INPUT_CACHE_VERSION = "stock-input-v3-full-a-share-name-index"


@st.cache_data(ttl=CACHE_TTL_STOCK_DATA, max_entries=64, show_spinner=False)
def get_cached_stock_data(symbol, period, market):
    """缓存股票数据获取"""
    try:
        return fetcher.get_stock_data(symbol, period=period, market=market)
    except Exception:
        logger.warning("缓存层获取股票数据失败: symbol=%s market=%s period=%s", symbol, market, period, exc_info=True)
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


@st.cache_data(ttl=CACHE_TTL_REALTIME, max_entries=64, show_spinner=False)
def get_cached_realtime_quote(symbol, market):
    """缓存实时行情"""
    try:
        return fetcher.get_realtime_quote(symbol, market)
    except Exception:
        logger.warning("缓存层获取实时行情失败: symbol=%s market=%s", symbol, market, exc_info=True)
        return None


@st.cache_data(ttl=CACHE_TTL_INTRADAY, show_spinner=False)
def get_cached_intraday_data(symbol, market):
    """缓存分时数据 — 60秒缓存，仅A股"""
    try:
        return fetcher.get_intraday_data(symbol, market)
    except Exception:
        logger.warning("缓存层获取分时数据失败: symbol=%s market=%s", symbol, market, exc_info=True)
        return None
