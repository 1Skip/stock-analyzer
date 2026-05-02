"""自选股管理模块测试"""
import json
import pytest
import streamlit as st


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def reset_watchlist():
    """每个测试前重置 watchlist 状态"""
    import streamlit as st
    st.session_state.clear()
    yield
    st.session_state.clear()


@pytest.fixture
def temp_watchlist_file(tmp_path, monkeypatch):
    """使用临时文件替代真实 watchlist.json"""
    temp_file = tmp_path / 'watchlist.json'
    monkeypatch.setattr('watchlist._WATCHLIST_FILE', str(temp_file))
    return temp_file


# ============================================================
# TestInitWatchlist
# ============================================================

class TestInitWatchlist:

    def test_initializes_empty_list(self):
        import watchlist
        watchlist.init_watchlist()
        assert st.session_state.watchlist == []

    def test_loads_from_file(self, temp_watchlist_file):
        import watchlist
        data = [
            {'symbol': '000001', 'name': '平安银行', 'market': 'CN'},
            {'symbol': 'AAPL', 'name': 'Apple', 'market': 'US'},
        ]
        temp_watchlist_file.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        watchlist.init_watchlist()
        assert len(st.session_state.watchlist) == 2
        assert st.session_state.watchlist[0]['symbol'] == '000001'

    def test_corrupted_file_returns_empty(self, temp_watchlist_file):
        import watchlist
        temp_watchlist_file.write_text('not valid json', encoding='utf-8')
        watchlist.init_watchlist()
        assert st.session_state.watchlist == []

    def test_idempotent(self):
        """多次调用不会重置已有数据"""
        import watchlist
        watchlist.init_watchlist()
        st.session_state.watchlist.append({'symbol': '000001', 'name': '测试', 'market': 'CN'})
        watchlist.init_watchlist()
        assert len(st.session_state.watchlist) == 1


# ============================================================
# TestAddToWatchlist
# ============================================================

class TestAddToWatchlist:

    def test_add_new_stock(self, temp_watchlist_file):
        from watchlist import add_to_watchlist
        success, msg = add_to_watchlist('000001', '平安银行', 'CN')
        assert success is True
        assert '成功' in msg

    def test_duplicate_returns_false(self, temp_watchlist_file):
        from watchlist import add_to_watchlist
        add_to_watchlist('000001', '平安银行', 'CN')
        success, msg = add_to_watchlist('000001', '平安银行', 'CN')
        assert success is False
        assert '已在' in msg

    def test_different_market_same_symbol_allowed(self, temp_watchlist_file):
        from watchlist import add_to_watchlist
        success1, _ = add_to_watchlist('000001', '平安银行', 'CN')
        success2, _ = add_to_watchlist('000001', '平安银行', 'HK')  # 不同市场
        assert success1 is True
        assert success2 is True

    def test_persists_to_file(self, temp_watchlist_file):
        from watchlist import add_to_watchlist
        add_to_watchlist('000001', '平安银行', 'CN')
        saved = json.loads(temp_watchlist_file.read_text(encoding='utf-8'))
        assert len(saved) == 1
        assert saved[0]['symbol'] == '000001'

    def test_structure_has_required_fields(self, temp_watchlist_file):
        from watchlist import add_to_watchlist, get_watchlist
        add_to_watchlist('000001', '平安银行', 'CN')
        items = get_watchlist()
        item = items[0]
        assert 'symbol' in item
        assert 'name' in item
        assert 'market' in item


# ============================================================
# TestRemoveFromWatchlist
# ============================================================

class TestRemoveFromWatchlist:

    def test_remove_existing(self, temp_watchlist_file):
        from watchlist import add_to_watchlist, remove_from_watchlist
        add_to_watchlist('000001', '平安银行', 'CN')
        success, msg = remove_from_watchlist('000001', 'CN')
        assert success is True

    def test_remove_nonexistent_is_idempotent(self, temp_watchlist_file):
        from watchlist import remove_from_watchlist
        success, msg = remove_from_watchlist('999999', 'CN')
        assert success is True

    def test_persists_after_remove(self, temp_watchlist_file):
        from watchlist import add_to_watchlist, remove_from_watchlist
        add_to_watchlist('000001', '平安银行', 'CN')
        add_to_watchlist('000002', '万科A', 'CN')
        remove_from_watchlist('000001', 'CN')
        saved = json.loads(temp_watchlist_file.read_text(encoding='utf-8'))
        assert len(saved) == 1
        assert saved[0]['symbol'] == '000002'


# ============================================================
# TestGetWatchlist
# ============================================================

class TestGetWatchlist:

    def test_returns_list(self):
        from watchlist import get_watchlist
        result = get_watchlist()
        assert isinstance(result, list)

    def test_returns_empty_when_no_items(self):
        from watchlist import get_watchlist
        assert get_watchlist() == []

    def test_returns_added_items(self, temp_watchlist_file):
        from watchlist import add_to_watchlist, get_watchlist
        add_to_watchlist('000001', '平安银行', 'CN')
        items = get_watchlist()
        assert len(items) == 1


# ============================================================
# TestClearWatchlist
# ============================================================

class TestClearWatchlist:

    def test_clears_all(self, temp_watchlist_file):
        from watchlist import add_to_watchlist, clear_watchlist, get_watchlist
        add_to_watchlist('000001', '平安银行', 'CN')
        add_to_watchlist('000002', '万科A', 'CN')
        clear_watchlist()
        assert get_watchlist() == []

    def test_clear_empty_no_error(self):
        from watchlist import clear_watchlist
        success, msg = clear_watchlist()
        assert success is True

    def test_persists_after_clear(self, temp_watchlist_file):
        from watchlist import add_to_watchlist, clear_watchlist
        add_to_watchlist('000001', '平安银行', 'CN')
        clear_watchlist()
        saved = json.loads(temp_watchlist_file.read_text(encoding='utf-8'))
        assert saved == []


# ============================================================
# TestIsInWatchlist
# ============================================================

class TestIsInWatchlist:

    def test_existing_returns_true(self, temp_watchlist_file):
        from watchlist import add_to_watchlist, is_in_watchlist
        add_to_watchlist('000001', '平安银行', 'CN')
        assert is_in_watchlist('000001', 'CN') is True

    def test_nonexistent_returns_false(self):
        from watchlist import is_in_watchlist
        assert is_in_watchlist('999999', 'CN') is False

    def test_different_market_returns_false(self, temp_watchlist_file):
        from watchlist import add_to_watchlist, is_in_watchlist
        add_to_watchlist('000001', '平安银行', 'CN')
        assert is_in_watchlist('000001', 'HK') is False


# ============================================================
# TestEdgeCases
# ============================================================

class TestEdgeCases:

    def test_empty_name(self, temp_watchlist_file):
        from watchlist import add_to_watchlist
        success, _ = add_to_watchlist('000001', '', 'CN')
        assert success is True

    def test_special_characters_in_name(self, temp_watchlist_file):
        from watchlist import add_to_watchlist, get_watchlist
        add_to_watchlist('000001', '测试股★☆', 'CN')
        items = get_watchlist()
        assert items[0]['name'] == '测试股★☆'


# ============================================================
# TestGetEntryHint
# ============================================================

class TestGetEntryHint:

    def test_near_support_lower_band(self):
        """价格在下轨附近 → 支撑位提示"""
        from watchlist import get_entry_hint
        ind = {'boll_upper': 15.0, 'boll_mid': 12.0, 'boll_lower': 10.0}
        hint = get_entry_hint(10.4, ind, '观望')
        assert '支撑位' in hint

    def test_near_resistance_upper_band(self):
        """价格在上轨附近 → 压力位提示"""
        from watchlist import get_entry_hint
        ind = {'boll_upper': 15.0, 'boll_mid': 12.0, 'boll_lower': 10.0}
        hint = get_entry_hint(14.6, ind, '观望')
        assert '压力位' in hint

    def test_mid_band_bullish(self):
        """中轨+偏多 → 建仓提示"""
        from watchlist import get_entry_hint
        ind = {'boll_upper': 15.0, 'boll_mid': 12.0, 'boll_lower': 10.0}
        hint = get_entry_hint(12.5, ind, '偏多信号')
        assert '建仓' in hint or '偏多' in hint

    def test_mid_band_bearish(self):
        """中轨+偏空 → 等待提示"""
        from watchlist import get_entry_hint
        ind = {'boll_upper': 15.0, 'boll_mid': 12.0, 'boll_lower': 10.0}
        hint = get_entry_hint(12.5, ind, '偏空信号')
        assert '偏空' in hint or '企稳' in hint

    def test_weak_zone(self):
        """价格偏弱区间 → 金叉提示"""
        from watchlist import get_entry_hint
        ind = {'boll_upper': 15.0, 'boll_mid': 12.0, 'boll_lower': 10.0}
        hint = get_entry_hint(11.5, ind, '观望')  # position=0.3, 0.20~0.35
        assert '弱' in hint or '金叉' in hint

    def test_strong_zone(self):
        """价格偏强区间 → 风险提示"""
        from watchlist import get_entry_hint
        ind = {'boll_upper': 15.0, 'boll_mid': 12.0, 'boll_lower': 10.0}
        hint = get_entry_hint(13.5, ind, '观望')  # position=0.7, 0.65~0.80
        assert '强' in hint or '高位' in hint

    def test_missing_indicators(self):
        """缺失指标 → 数据不足"""
        from watchlist import get_entry_hint
        hint = get_entry_hint(12.0, {}, '观望')
        assert '数据不足' in hint

    def test_zero_band_range(self):
        """布林带宽度为零 → 波动极小"""
        from watchlist import get_entry_hint
        ind = {'boll_upper': 10.0, 'boll_mid': 10.0, 'boll_lower': 10.0}
        hint = get_entry_hint(10.0, ind, '观望')
        assert '波动极小' in hint


# ============================================================
# TestGetWatchlistSummary
# ============================================================

class TestGetWatchlistSummary:

    def test_returns_list(self, monkeypatch):
        """正常返回列表"""
        import pandas as pd
        from data_fetcher import StockDataFetcher

        dates = pd.date_range('2025-06-01', periods=30, freq='B')
        n = 30
        mock_df = pd.DataFrame({
            'open': [10]*n, 'high': [10.5]*n, 'low': [9.5]*n, 'close': [10]*n,
            'volume': [1000000]*n,
        }, index=dates)

        monkeypatch.setattr(StockDataFetcher, 'get_stock_data',
                           lambda self, symbol, period, market: mock_df)

        from watchlist import get_watchlist_summary
        items = [{'symbol': '000001', 'name': '平安银行', 'market': 'CN'}]
        results = get_watchlist_summary(items)
        assert len(results) == 1
        assert results[0]['symbol'] == '000001'
        assert results[0]['price'] is not None

    def test_multiple_stocks(self, monkeypatch):
        """多只股票各自返回独立条目"""
        import pandas as pd
        from data_fetcher import StockDataFetcher

        dates = pd.date_range('2025-06-01', periods=30, freq='B')
        n = 30
        mock_df = pd.DataFrame({
            'open': [10]*n, 'high': [10.5]*n, 'low': [9.5]*n, 'close': [10]*n,
            'volume': [1000000]*n,
        }, index=dates)

        monkeypatch.setattr(StockDataFetcher, 'get_stock_data',
                           lambda self, symbol, period, market: mock_df)

        from watchlist import get_watchlist_summary
        items = [
            {'symbol': '000001', 'name': '平安银行', 'market': 'CN'},
            {'symbol': '600519', 'name': '贵州茅台', 'market': 'CN'},
        ]
        results = get_watchlist_summary(items)
        assert len(results) == 2
        assert results[0]['symbol'] == '000001'
        assert results[1]['symbol'] == '600519'

    def test_data_insufficient(self, monkeypatch):
        """数据不足 → 设置 error 字段"""
        import pandas as pd
        from data_fetcher import StockDataFetcher

        # 只有5行数据，不足 get_signals 最低要求
        dates = pd.date_range('2025-06-01', periods=5, freq='B')
        n = 5
        mock_df = pd.DataFrame({
            'open': [10]*n, 'high': [10.5]*n, 'low': [9.5]*n, 'close': [10]*n,
            'volume': [1000000]*n,
        }, index=dates)

        monkeypatch.setattr(StockDataFetcher, 'get_stock_data',
                           lambda self, symbol, period, market: mock_df)

        from watchlist import get_watchlist_summary
        items = [{'symbol': '000001', 'name': '平安银行', 'market': 'CN'}]
        results = get_watchlist_summary(items)
        assert results[0]['error'] is not None

    def test_exception_is_caught(self, monkeypatch):
        """数据获取异常 → 设置 error 字段"""
        from data_fetcher import StockDataFetcher
        monkeypatch.setattr(StockDataFetcher, 'get_stock_data',
                           lambda self, symbol, period, market: (_ for _ in ()).throw(Exception("网络错误")))

        from watchlist import get_watchlist_summary
        items = [{'symbol': '000001', 'name': '平安银行', 'market': 'CN'}]
        results = get_watchlist_summary(items)
        assert results[0]['error'] is not None

    def test_empty_watchlist(self):
        """空列表返回空列表"""
        from watchlist import get_watchlist_summary
        results = get_watchlist_summary([])
        assert results == []
