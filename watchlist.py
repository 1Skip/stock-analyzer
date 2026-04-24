"""
自选股管理模块
使用 Streamlit session state 存储用户的自选股列表
"""
import streamlit as st


def init_watchlist():
    """初始化自选股列表"""
    if 'watchlist' not in st.session_state:
        st.session_state.watchlist = []


def add_to_watchlist(symbol, name, market='CN'):
    """添加股票到自选股"""
    init_watchlist()

    # 检查是否已存在
    for item in st.session_state.watchlist:
        if item['symbol'] == symbol and item['market'] == market:
            return False, "该股票已在自选股中"

    # 添加到列表
    st.session_state.watchlist.append({
        'symbol': symbol,
        'name': name,
        'market': market
    })
    return True, "添加成功"


def remove_from_watchlist(symbol, market='CN'):
    """从自选股中移除"""
    init_watchlist()

    st.session_state.watchlist = [
        item for item in st.session_state.watchlist
        if not (item['symbol'] == symbol and item['market'] == market)
    ]
    return True, "移除成功"


def get_watchlist():
    """获取自选股列表"""
    init_watchlist()
    return st.session_state.watchlist


def clear_watchlist():
    """清空自选股"""
    init_watchlist()
    st.session_state.watchlist = []
    return True, "已清空"


def is_in_watchlist(symbol, market='CN'):
    """检查股票是否在自选股中"""
    init_watchlist()
    return any(
        item['symbol'] == symbol and item['market'] == market
        for item in st.session_state.watchlist
    )
