"""
自选股管理模块
持久化到 watchlist.json，同时维护 session_state 缓存
"""
import streamlit as st
import json
import os
from threading import Lock

_WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), 'watchlist.json')
_save_lock = Lock()


def _load_from_file():
    """从 JSON 文件加载自选股"""
    if os.path.exists(_WATCHLIST_FILE):
        try:
            with open(_WATCHLIST_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_to_file(watchlist):
    """保存自选股到 JSON 文件"""
    with _save_lock:
        try:
            with open(_WATCHLIST_FILE, 'w', encoding='utf-8') as f:
                json.dump(watchlist, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


def init_watchlist():
    """初始化自选股列表：首次调用从文件加载，后续使用 session_state"""
    if 'watchlist' not in st.session_state:
        st.session_state.watchlist = _load_from_file()


def add_to_watchlist(symbol, name, market='CN'):
    """添加股票到自选股"""
    init_watchlist()
    for item in st.session_state.watchlist:
        if item['symbol'] == symbol and item['market'] == market:
            return False, "该股票已在自选股中"
    st.session_state.watchlist.append({
        'symbol': symbol,
        'name': name,
        'market': market
    })
    _save_to_file(st.session_state.watchlist)
    return True, "添加成功"


def remove_from_watchlist(symbol, market='CN'):
    """从自选股中移除"""
    init_watchlist()
    st.session_state.watchlist = [
        item for item in st.session_state.watchlist
        if not (item['symbol'] == symbol and item['market'] == market)
    ]
    _save_to_file(st.session_state.watchlist)
    return True, "移除成功"


def get_watchlist():
    """获取自选股列表"""
    init_watchlist()
    return st.session_state.watchlist


def clear_watchlist():
    """清空自选股"""
    init_watchlist()
    st.session_state.watchlist = []
    _save_to_file(st.session_state.watchlist)
    return True, "已清空"


def is_in_watchlist(symbol, market='CN'):
    """检查股票是否在自选股中"""
    init_watchlist()
    return any(
        item['symbol'] == symbol and item['market'] == market
        for item in st.session_state.watchlist
    )
