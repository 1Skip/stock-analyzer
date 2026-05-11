"""缓存数据获取层 — Streamlit @st.cache_data 封装"""
import streamlit as st
from data_fetcher import StockDataFetcher
from config import CACHE_TTL_REALTIME, CACHE_TTL_STOCK_DATA, CACHE_TTL_STOCK_INFO


fetcher = StockDataFetcher()


@st.cache_data(ttl=CACHE_TTL_STOCK_DATA, max_entries=64, show_spinner=False)
def get_cached_stock_data(symbol, period, market):
    """缓存股票数据获取"""
    try:
        return fetcher.get_stock_data(symbol, period=period, market=market)
    except Exception:
        return None


@st.cache_data(ttl=CACHE_TTL_STOCK_INFO, max_entries=128, show_spinner=False)
def get_cached_stock_info(symbol, market):
    """缓存股票基本信息"""
    try:
        return fetcher.get_stock_info(symbol, market)
    except Exception:
        return {}


@st.cache_data(ttl=CACHE_TTL_REALTIME, max_entries=64, show_spinner=False)
def get_cached_realtime_quote(symbol, market):
    """缓存实时行情"""
    try:
        return fetcher.get_realtime_quote(symbol, market)
    except Exception:
        return None


@st.cache_data(ttl=60, show_spinner=False)
def get_cached_intraday_data(symbol, market):
    """缓存分时数据 — 60秒缓存，仅A股"""
    try:
        return fetcher.get_intraday_data(symbol, market)
    except Exception:
        return None
