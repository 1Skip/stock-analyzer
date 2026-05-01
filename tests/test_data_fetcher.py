"""数据获取模块测试"""
import pytest
import pandas as pd
import numpy as np
import json
import os
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock


# ============================================================
# 辅助函数
# ============================================================

def _make_ohlcv_df(days=60, base_price=10.0):
    """生成OHLCV DataFrame，列名小写"""
    end_date = pd.Timestamp.now().normalize()
    # 确保 end_date 是工作日，避免 pandas freq='B' 遇周末生成 N-1 个日期
    if end_date.weekday() >= 5:
        end_date = end_date - pd.Timedelta(days=end_date.weekday() - 4)
    dates = pd.date_range(end=end_date, periods=days, freq='B')
    np.random.seed(days)
    data = {
        'open': np.round(base_price + np.random.uniform(-0.3, 0.3, days), 2),
        'high': np.round(base_price + np.random.uniform(0.2, 0.6, days), 2),
        'low': np.round(base_price + np.random.uniform(-0.6, -0.1, days), 2),
        'close': np.round(base_price + np.random.uniform(-0.3, 0.3, days), 2),
        'volume': np.random.randint(1000000, 10000000, days),
    }
    df = pd.DataFrame(data, index=dates)
    for i in range(days):
        o, c = df.iloc[i]['open'], df.iloc[i]['close']
        df.iloc[i, df.columns.get_loc('high')] = max(o, c) + abs(np.random.uniform(0, 0.3))
        df.iloc[i, df.columns.get_loc('low')] = min(o, c) - abs(np.random.uniform(0, 0.3))
    return df


def _make_spot_df():
    """生成类似 AKShare spot 的 DataFrame"""
    return pd.DataFrame([
        {'代码': '000001', '名称': '平安银行', '最新价': 12.50, '今开': 12.30,
         '最高': 12.60, '最低': 12.20, '昨收': 12.00, '成交量': 50000000},
        {'代码': '000002', '名称': '万科A', '最新价': 15.00, '今开': 14.80,
         '最高': 15.10, '最低': 14.70, '昨收': 14.50, '成交量': 30000000},
    ])


# ============================================================
# 重置类级别状态
# ============================================================

@pytest.fixture(autouse=True)
def reset_fetcher_state():
    """每个测试前后重置 StockDataFetcher 类级别状态"""
    from data_fetcher import StockDataFetcher
    orig_health = {k: v.copy() for k, v in StockDataFetcher._health_status.items()}
    orig_spot = StockDataFetcher._spot_cache
    orig_spot_time = StockDataFetcher._spot_cache_time
    orig_locks = StockDataFetcher._request_locks.copy()

    yield

    StockDataFetcher._health_status = orig_health
    StockDataFetcher._spot_cache = orig_spot
    StockDataFetcher._spot_cache_time = orig_spot_time
    StockDataFetcher._request_locks = orig_locks
    # 清除 env
    os.environ.pop('STOCK_DATA_SOURCE', None)


# ============================================================
# TestInitAndConfig
# ============================================================

class TestInitAndConfig:

    def test_init_default_preferred_source(self):
        from data_fetcher import StockDataFetcher
        os.environ.pop('STOCK_DATA_SOURCE', None)
        fetcher = StockDataFetcher()
        assert fetcher.preferred_source in ('auto', 'akshare', 'sina', 'yfinance')

    def test_init_max_retries(self):
        from data_fetcher import StockDataFetcher
        fetcher = StockDataFetcher()
        assert fetcher.max_retries == 3

    def test_get_preferred_source(self):
        from data_fetcher import StockDataFetcher
        os.environ.pop('STOCK_DATA_SOURCE', None)
        fetcher = StockDataFetcher()
        assert fetcher.get_preferred_source() == 'auto'

    def test_set_preferred_source_valid(self):
        from data_fetcher import StockDataFetcher
        os.environ.pop('STOCK_DATA_SOURCE', None)
        fetcher = StockDataFetcher()
        assert fetcher.set_preferred_source('akshare') is True
        assert fetcher.get_preferred_source() == 'akshare'

    def test_set_preferred_source_invalid_returns_false(self):
        from data_fetcher import StockDataFetcher
        os.environ.pop('STOCK_DATA_SOURCE', None)
        fetcher = StockDataFetcher()
        assert fetcher.set_preferred_source('invalid') is False
        assert fetcher.get_preferred_source() == 'auto'

    def test_env_var_sets_preferred_source(self, monkeypatch):
        monkeypatch.setenv('STOCK_DATA_SOURCE', 'sina')
        import importlib
        import data_fetcher
        importlib.reload(data_fetcher)
        fetcher = data_fetcher.StockDataFetcher()
        assert fetcher.preferred_source == 'sina'


# ============================================================
# TestHealthStatus
# ============================================================

class TestHealthStatus:

    def test_initial_all_healthy(self):
        from data_fetcher import StockDataFetcher
        fetcher = StockDataFetcher()
        health = fetcher.check_health()
        for source in ('akshare', 'sina', 'yfinance'):
            assert health[source]['healthy'] is True
            assert health[source]['fail_count'] == 0

    def test_single_failure_not_unhealthy(self):
        from data_fetcher import StockDataFetcher
        fetcher = StockDataFetcher()
        fetcher._update_health_status('akshare', False)
        assert fetcher.check_health()['akshare']['healthy'] is True

    def test_three_failures_marks_unhealthy(self):
        from data_fetcher import StockDataFetcher
        fetcher = StockDataFetcher()
        for _ in range(3):
            fetcher._update_health_status('sina', False)
        assert fetcher.check_health()['sina']['healthy'] is False

    def test_success_resets_fail_count(self):
        from data_fetcher import StockDataFetcher
        fetcher = StockDataFetcher()
        fetcher._update_health_status('yfinance', False)
        fetcher._update_health_status('yfinance', False)
        fetcher._update_health_status('yfinance', True)
        health = fetcher.check_health()
        assert health['yfinance']['fail_count'] == 1
        assert health['yfinance']['healthy'] is True

    def test_last_check_updated_on_failure(self):
        from data_fetcher import StockDataFetcher
        fetcher = StockDataFetcher()
        fetcher._update_health_status('akshare', False)
        assert fetcher.check_health()['akshare']['last_check'] is not None

    def test_health_check_returns_new_dict(self):
        from data_fetcher import StockDataFetcher
        fetcher = StockDataFetcher()
        h1 = fetcher.check_health()
        h2 = fetcher.check_health()
        assert h1 is not h2

    def test_recovery_via_update(self):
        from data_fetcher import StockDataFetcher
        fetcher = StockDataFetcher()
        for _ in range(5):
            fetcher._update_health_status('akshare', False)
        assert StockDataFetcher._health_status['akshare']['healthy'] is False
        for _ in range(10):
            fetcher._update_health_status('akshare', True)
        assert StockDataFetcher._health_status['akshare']['healthy'] is True
        assert StockDataFetcher._health_status['akshare']['fail_count'] == 0


# ============================================================
# TestOfflineCache - 用直接文件操作测试
# ============================================================

class TestOfflineCache:

    def test_save_and_read_file(self, tmp_path):
        """直接验证缓存写入文件和读取"""
        from data_fetcher import StockDataFetcher
        cache_file = tmp_path / 'cache.json'
        StockDataFetcher._offline_cache_file = str(cache_file)
        fetcher = StockDataFetcher()
        df = _make_ohlcv_df(days=30, base_price=10.0)
        fetcher._save_offline_cache('000001', df)

        assert cache_file.exists()
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        assert '000001' in cache_data
        assert 'data' in cache_data['000001']
        raw = cache_data['000001']['data']
        assert isinstance(raw, str)
        # 用 StringIO 避开 pandas 2.x 的 file/path 检测问题
        import io
        restored = pd.read_json(io.StringIO(raw), orient='split')
        assert len(restored) == 30

    def test_load_nonexistent_symbol(self, tmp_path):
        from data_fetcher import StockDataFetcher
        cache_file = tmp_path / 'cache.json'
        StockDataFetcher._offline_cache_file = str(cache_file)
        fetcher = StockDataFetcher()
        df = _make_ohlcv_df(days=30, base_price=10.0)
        fetcher._save_offline_cache('000001', df)
        assert fetcher._load_offline_cache('999999') is None

    def test_load_expired_cache(self, tmp_path):
        from data_fetcher import StockDataFetcher
        cache_file = tmp_path / 'cache.json'
        df = _make_ohlcv_df(days=30, base_price=10.0)
        cache_data = {
            '000001': {
                'timestamp': (datetime.now() - timedelta(hours=25)).isoformat(),
                'data': df.to_json(orient='split', date_format='iso'),
            }
        }
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f)

        StockDataFetcher._offline_cache_file = str(cache_file)
        fetcher = StockDataFetcher()
        assert fetcher._load_offline_cache('000001', max_age_hours=24) is None

    def test_cache_file_not_exists(self, tmp_path):
        from data_fetcher import StockDataFetcher
        StockDataFetcher._offline_cache_file = str(tmp_path / 'nonexistent.json')
        fetcher = StockDataFetcher()
        assert fetcher._load_offline_cache('000001') is None

    def test_corrupted_cache_handled(self, tmp_path):
        from data_fetcher import StockDataFetcher
        cache_file = tmp_path / 'cache.json'
        with open(cache_file, 'w', encoding='utf-8') as f:
            f.write('this is not json')
        StockDataFetcher._offline_cache_file = str(cache_file)
        fetcher = StockDataFetcher()
        assert fetcher._load_offline_cache('000001') is None

    def test_max_entries_eviction(self, tmp_path):
        from data_fetcher import StockDataFetcher
        cache_file = tmp_path / 'cache.json'
        StockDataFetcher._offline_cache_file = str(cache_file)
        fetcher = StockDataFetcher()
        # 每次写入后确认文件存在再继续
        for i in range(25):
            df = _make_ohlcv_df(days=5, base_price=float(10 + i))
            fetcher._save_offline_cache(f'stock_{i}', df)
            time.sleep(0.02)
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        assert len(cache_data) <= 20

    def test_saved_cache_has_data(self, tmp_path):
        from data_fetcher import StockDataFetcher
        cache_file = tmp_path / 'cache.json'
        StockDataFetcher._offline_cache_file = str(cache_file)
        fetcher = StockDataFetcher()
        df = _make_ohlcv_df(days=30, base_price=10.0)
        fetcher._save_offline_cache('000001', df)
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        assert '000001' in cache_data
        assert isinstance(cache_data['000001']['data'], str)


# ============================================================
# TestGetStockData - 核心数据获取
# ============================================================

class TestGetStockDataCN:

    def test_akshare_success_path(self, monkeypatch):
        from data_fetcher import StockDataFetcher
        df = _make_ohlcv_df(days=60, base_price=10.0)

        def mock_ak_daily(symbol, start_date, end_date, adjust):
            result = df.copy()
            result['date'] = result.index
            return result.reset_index(drop=True)

        monkeypatch.setattr('data_fetcher.AKSHARE_AVAILABLE', True)
        monkeypatch.setattr('data_fetcher.ak.stock_zh_a_daily', mock_ak_daily)
        # 禁用离线缓存
        monkeypatch.setattr('data_fetcher.StockDataFetcher._save_offline_cache',
                            lambda self, s, d: None)

        fetcher = StockDataFetcher()
        fetcher.set_preferred_source('akshare')
        result = fetcher.get_stock_data('000001', period='1y', market='CN')
        assert result is not None
        assert len(result) >= 30
        assert 'AKShare' in result.attrs.get('data_source', '')

    def test_falls_back_to_sina_when_akshare_fails(self, monkeypatch):
        from data_fetcher import StockDataFetcher
        monkeypatch.setattr('data_fetcher.AKSHARE_AVAILABLE', True)
        monkeypatch.setattr('data_fetcher.ak.stock_zh_a_daily',
                            lambda **kw: exec('raise Exception("AKShare error")'))

        df = _make_ohlcv_df(days=60, base_price=10.0)
        sina_json = []
        for idx, row in df.iterrows():
            sina_json.append({
                'day': idx.strftime('%Y-%m-%d'),
                'open': str(row['open']),
                'high': str(row['high']),
                'low': str(row['low']),
                'close': str(row['close']),
                'volume': str(int(row['volume'])),
            })

        def mock_get(url, headers=None, timeout=None, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.text = json.dumps(sina_json)
            return resp

        monkeypatch.setattr('data_fetcher.requests.get', mock_get)
        monkeypatch.setattr('data_fetcher.StockDataFetcher._save_offline_cache',
                            lambda self, s, d: None)

        fetcher = StockDataFetcher()
        fetcher.set_preferred_source('auto')
        result = fetcher.get_stock_data('000001', period='1y', market='CN')
        assert result is not None
        assert len(result) >= 10

    def test_all_online_sources_fail_returns_none(self, monkeypatch):
        from data_fetcher import StockDataFetcher
        monkeypatch.setattr('data_fetcher.AKSHARE_AVAILABLE', False)
        monkeypatch.setattr('data_fetcher.requests.get',
                            lambda url, **kw: exec('raise Exception("network error")'))

        fetcher = StockDataFetcher()
        monkeypatch.setattr(fetcher, '_load_offline_cache', lambda s: None)
        monkeypatch.setattr(fetcher, '_save_offline_cache', lambda s, d: None)
        assert fetcher.get_stock_data('000001', period='1y', market='CN') is None

    def test_offline_cache_as_last_resort(self, monkeypatch, tmp_path):
        from data_fetcher import StockDataFetcher
        cache_file = tmp_path / 'cache.json'
        StockDataFetcher._offline_cache_file = str(cache_file)

        # 先写入缓存
        df = _make_ohlcv_df(days=60, base_price=10.0)
        fetcher = StockDataFetcher()
        fetcher._save_offline_cache('000001', df)

        # 禁用所有在线源
        monkeypatch.setattr('data_fetcher.AKSHARE_AVAILABLE', False)
        monkeypatch.setattr('data_fetcher.requests.get',
                            lambda url, **kw: exec('raise Exception("no network")'))

        class MockTicker:
            def __init__(self, symbol):
                pass
            def history(self, period='1y', **kwargs):
                return pd.DataFrame()

        monkeypatch.setattr('data_fetcher.yf.Ticker', MockTicker)

        result = fetcher.get_stock_data('000001', period='1y', market='CN')
        assert result is not None
        assert len(result) == 60

    def test_data_source_attribution(self, monkeypatch):
        from data_fetcher import StockDataFetcher
        df = _make_ohlcv_df(days=60, base_price=10.0)

        def mock_ak_daily(symbol, start_date, end_date, adjust):
            result = df.copy()
            result['date'] = result.index
            return result.reset_index(drop=True)

        monkeypatch.setattr('data_fetcher.AKSHARE_AVAILABLE', True)
        monkeypatch.setattr('data_fetcher.ak.stock_zh_a_daily', mock_ak_daily)
        monkeypatch.setattr('data_fetcher.StockDataFetcher._save_offline_cache',
                            lambda self, s, d: None)

        fetcher = StockDataFetcher()
        fetcher.set_preferred_source('akshare')
        result = fetcher.get_stock_data('000001', period='1y', market='CN')
        assert 'data_source' in result.attrs
        assert 'AKShare' in result.attrs['data_source']

    def test_columns_normalized_to_lowercase(self, monkeypatch):
        from data_fetcher import StockDataFetcher
        df = _make_ohlcv_df(days=60, base_price=10.0)

        def mock_ak_daily(symbol, start_date, end_date, adjust):
            result = df.copy()
            result['date'] = result.index
            return result.reset_index(drop=True)

        monkeypatch.setattr('data_fetcher.AKSHARE_AVAILABLE', True)
        monkeypatch.setattr('data_fetcher.ak.stock_zh_a_daily', mock_ak_daily)
        monkeypatch.setattr('data_fetcher.StockDataFetcher._save_offline_cache',
                            lambda self, s, d: None)

        fetcher = StockDataFetcher()
        fetcher.set_preferred_source('akshare')
        result = fetcher.get_stock_data('000001', period='1y', market='CN')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            assert col in result.columns

    def test_shanghai_prefix_uses_sh(self, monkeypatch):
        from data_fetcher import StockDataFetcher
        df = _make_ohlcv_df(days=60, base_price=10.0)
        captured = []

        def mock_ak_daily(symbol, start_date, end_date, adjust):
            captured.append(symbol)
            result = df.copy()
            result['date'] = result.index
            return result.reset_index(drop=True)

        monkeypatch.setattr('data_fetcher.AKSHARE_AVAILABLE', True)
        monkeypatch.setattr('data_fetcher.ak.stock_zh_a_daily', mock_ak_daily)
        monkeypatch.setattr('data_fetcher.StockDataFetcher._save_offline_cache',
                            lambda self, s, d: None)

        fetcher = StockDataFetcher()
        fetcher.set_preferred_source('akshare')
        fetcher.get_stock_data('600001', period='1y', market='CN')
        assert len(captured) > 0 and captured[0].startswith('sh')

    def test_shenzhen_prefix_uses_sz(self, monkeypatch):
        from data_fetcher import StockDataFetcher
        df = _make_ohlcv_df(days=60, base_price=10.0)
        captured = []

        def mock_ak_daily(symbol, start_date, end_date, adjust):
            captured.append(symbol)
            result = df.copy()
            result['date'] = result.index
            return result.reset_index(drop=True)

        monkeypatch.setattr('data_fetcher.AKSHARE_AVAILABLE', True)
        monkeypatch.setattr('data_fetcher.ak.stock_zh_a_daily', mock_ak_daily)
        monkeypatch.setattr('data_fetcher.StockDataFetcher._save_offline_cache',
                            lambda self, s, d: None)

        fetcher = StockDataFetcher()
        fetcher.set_preferred_source('akshare')
        fetcher.get_stock_data('000001', period='1y', market='CN')
        assert len(captured) > 0 and captured[0].startswith('sz')


class TestGetStockDataHK:

    def test_hk_yfinance_success(self, monkeypatch):
        from data_fetcher import StockDataFetcher
        df = _make_ohlcv_df(days=60, base_price=50.0)

        class MockTicker:
            def __init__(self, symbol):
                pass
            def history(self, period='1y', interval='1d'):
                return df.copy()

        monkeypatch.setattr('data_fetcher.yf.Ticker', MockTicker)

        fetcher = StockDataFetcher()
        result = fetcher.get_stock_data('00700', period='1y', market='HK')
        assert result is not None
        assert len(result) == 60

    def test_hk_yfinance_empty_returns_none(self, monkeypatch, tmp_path):
        from data_fetcher import StockDataFetcher

        class MockTicker:
            def __init__(self, symbol):
                pass
            def history(self, period='1y', interval='1d'):
                return pd.DataFrame()

        monkeypatch.setattr('data_fetcher.yf.Ticker', MockTicker)

        fetcher = StockDataFetcher()
        # 防止读到项目目录下的真实离线缓存
        StockDataFetcher._offline_cache_file = str(tmp_path / 'nonexistent.json')
        assert fetcher.get_stock_data('00700', period='1y', market='HK') is None


class TestGetStockDataUS:

    def test_us_yfinance_success(self, monkeypatch):
        from data_fetcher import StockDataFetcher
        df = _make_ohlcv_df(days=60, base_price=150.0)

        class MockTicker:
            def __init__(self, symbol):
                pass
            def history(self, period='1y', interval='1d'):
                return df.copy()

        monkeypatch.setattr('data_fetcher.yf.Ticker', MockTicker)

        fetcher = StockDataFetcher()
        result = fetcher.get_stock_data('AAPL', period='1y', market='US')
        assert result is not None
        assert len(result) == 60

    def test_us_data_source_label(self, monkeypatch):
        from data_fetcher import StockDataFetcher
        df = _make_ohlcv_df(days=60, base_price=150.0)

        class MockTicker:
            def __init__(self, symbol):
                pass
            def history(self, period='1y', interval='1d'):
                return df.copy()

        monkeypatch.setattr('data_fetcher.yf.Ticker', MockTicker)

        fetcher = StockDataFetcher()
        result = fetcher.get_stock_data('AAPL', period='1y', market='US')
        assert 'Yahoo Finance' in result.attrs.get('data_source', '')


# ============================================================
# TestGetStockInfo
# ============================================================

class TestGetStockInfo:

    def test_cn_from_mapping(self):
        from data_fetcher import StockDataFetcher
        fetcher = StockDataFetcher()
        info = fetcher.get_stock_info('000001', market='CN')
        assert info['shortName'] == '平安银行'

    def test_cn_unknown_returns_symbol(self):
        from data_fetcher import StockDataFetcher
        fetcher = StockDataFetcher()
        info = fetcher.get_stock_info('XYZ999', market='CN')
        assert info['symbol'] == 'XYZ999'


# ============================================================
# TestGetStockName
# ============================================================

class TestGetStockName:

    def test_cn_from_spot(self, monkeypatch):
        from data_fetcher import StockDataFetcher
        monkeypatch.setattr(StockDataFetcher, '_get_spot_snapshot',
                            classmethod(lambda cls: _make_spot_df()))
        fetcher = StockDataFetcher()
        assert fetcher.get_stock_name('000001', market='CN') == '平安银行'

    def test_cn_falls_back_to_mapping(self, monkeypatch):
        from data_fetcher import StockDataFetcher
        monkeypatch.setattr(StockDataFetcher, '_get_spot_snapshot',
                            classmethod(lambda cls: None))

        def mock_get(url, headers=None, timeout=None, **kwargs):
            resp = MagicMock()
            resp.status_code = 404
            return resp

        monkeypatch.setattr('data_fetcher.requests.get', mock_get)

        fetcher = StockDataFetcher()
        name = fetcher.get_stock_name('000001', market='CN')
        from data_fetcher import CN_STOCK_NAMES_EXTENDED
        assert name == CN_STOCK_NAMES_EXTENDED.get('000001')

    def test_cn_unknown_returns_symbol(self, monkeypatch):
        from data_fetcher import StockDataFetcher
        monkeypatch.setattr(StockDataFetcher, '_get_spot_snapshot',
                            classmethod(lambda cls: None))

        def mock_get(url, headers=None, timeout=None, **kwargs):
            resp = MagicMock()
            resp.status_code = 404
            return resp

        monkeypatch.setattr('data_fetcher.requests.get', mock_get)

        fetcher = StockDataFetcher()
        name = fetcher.get_stock_name('XYZ999', market='CN')
        assert name == 'XYZ999'


# ============================================================
# TestGetRealtimeQuote
# ============================================================

class TestGetRealtimeQuote:

    def test_cn_from_akshare_spot(self, monkeypatch):
        from data_fetcher import StockDataFetcher
        monkeypatch.setattr(StockDataFetcher, '_get_spot_snapshot',
                            classmethod(lambda cls: _make_spot_df()))
        fetcher = StockDataFetcher()
        quote = fetcher.get_realtime_quote('000001', market='CN')
        assert quote is not None
        assert quote['price'] == 12.50
        expected_change = (12.50 / 12.00 - 1) * 100
        assert abs(quote['change'] - expected_change) < 0.01

    def test_cn_from_sina_shenzhen(self, monkeypatch):
        from data_fetcher import StockDataFetcher
        monkeypatch.setattr(StockDataFetcher, '_get_spot_snapshot',
                            classmethod(lambda cls: None))

        fields = ['平安银行'] + ['0'] * 32
        fields[1] = '12.30'
        fields[2] = '12.00'
        fields[3] = '12.50'
        fields[4] = '12.60'
        fields[5] = '12.20'
        fields[8] = '50000000'

        def mock_get(url, headers=None, timeout=None, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.text = '"{}"'.format(','.join(fields))
            return resp

        monkeypatch.setattr('data_fetcher.requests.get', mock_get)
        # Mock yfinance 以备回退
        monkeypatch.setattr('data_fetcher.yf.Ticker', lambda s: exec('raise Exception("no")'))

        fetcher = StockDataFetcher()
        quote = fetcher.get_realtime_quote('000001', market='CN')
        assert quote is not None
        assert quote['price'] == 12.50
        expected_change = (12.50 / 12.00 - 1) * 100
        assert abs(quote['change'] - expected_change) < 0.01

    def test_cn_shanghai_fallback(self, monkeypatch):
        from data_fetcher import StockDataFetcher
        monkeypatch.setattr(StockDataFetcher, '_get_spot_snapshot',
                            classmethod(lambda cls: None))

        fields = ['邯郸钢铁'] + ['0'] * 32
        fields[1] = '5.00'
        fields[2] = '4.80'
        fields[3] = '5.10'
        fields[4] = '5.20'
        fields[5] = '4.90'
        fields[8] = '30000000'

        def mock_get(url, headers=None, timeout=None, **kwargs):
            resp = MagicMock()
            if 'sz' in url:
                resp.status_code = 404
                resp.text = ''
            else:
                resp.status_code = 200
                resp.text = '"{}"'.format(','.join(fields))
            return resp

        monkeypatch.setattr('data_fetcher.requests.get', mock_get)
        monkeypatch.setattr('data_fetcher.yf.Ticker', lambda s: exec('raise Exception("no")'))

        fetcher = StockDataFetcher()
        quote = fetcher.get_realtime_quote('600001', market='CN')
        assert quote is not None
        assert quote['price'] == 5.10

    def test_all_sources_fail_returns_none(self, monkeypatch):
        from data_fetcher import StockDataFetcher
        monkeypatch.setattr(StockDataFetcher, '_get_spot_snapshot',
                            classmethod(lambda cls: None))
        monkeypatch.setattr('data_fetcher.requests.get',
                            lambda url, **kw: exec('raise Exception("network error")'))
        monkeypatch.setattr('data_fetcher.yf.Ticker', lambda s: exec('raise Exception("no")'))

        fetcher = StockDataFetcher()
        assert fetcher.get_realtime_quote('000001', market='CN') is None

    def test_hk_realtime_uses_ticker_info(self, monkeypatch):
        from data_fetcher import StockDataFetcher
        # yfinance 返回大写列名
        df = _make_ohlcv_df(days=5, base_price=50.0)
        df.columns = [c.capitalize() for c in df.columns]

        class MockTicker:
            def __init__(self, symbol):
                self.info = {'shortName': 'Tencent'}
            def history(self, period='5d'):
                return df.copy()

        monkeypatch.setattr('data_fetcher.yf.Ticker', MockTicker)

        fetcher = StockDataFetcher()
        quote = fetcher.get_realtime_quote('00700', market='HK')
        assert quote is not None
        assert quote['name'] == 'Tencent'


# ============================================================
# TestFetchMultipleStocks
# ============================================================

class TestFetchMultipleStocks:

    def test_fetch_multiple(self, monkeypatch):
        from data_fetcher import StockDataFetcher
        df = _make_ohlcv_df(days=60, base_price=150.0)

        class MockTicker:
            def __init__(self, symbol):
                pass
            def history(self, period='3mo', interval='1d'):
                return df.copy()

        monkeypatch.setattr('data_fetcher.yf.Ticker', MockTicker)

        symbols = [{'code': 'AAPL', 'name': 'Apple'}, {'code': 'GOOGL', 'name': 'Google'}]
        results = StockDataFetcher.fetch_multiple_stocks(symbols, market='US')
        assert isinstance(results, dict)
        assert len(results) == 2
        assert results['AAPL']['success'] is True

    def test_fetch_empty(self):
        from data_fetcher import StockDataFetcher
        assert StockDataFetcher.fetch_multiple_stocks([], market='US') == {}

    def test_fetch_mixed(self, monkeypatch):
        from data_fetcher import StockDataFetcher

        class MockTicker:
            def __init__(self, symbol):
                self._symbol = symbol
            def history(self, period='3mo', interval='1d'):
                if 'FAIL' in self._symbol:
                    return pd.DataFrame()
                return _make_ohlcv_df(days=60, base_price=150.0).copy()

        monkeypatch.setattr('data_fetcher.yf.Ticker', MockTicker)

        symbols = [{'code': 'AAPL', 'name': 'Apple'}, {'code': 'FAIL', 'name': 'Bad'}]
        results = StockDataFetcher.fetch_multiple_stocks(symbols, market='US')
        assert len(results) == 2
        assert results['AAPL']['success'] is True
        assert results['FAIL']['success'] is False


# ============================================================
# TestModuleConstants
# ============================================================

class TestModuleConstants:

    def test_cn_names_count(self):
        from data_fetcher import CN_STOCK_NAMES_EXTENDED
        assert len(CN_STOCK_NAMES_EXTENDED) >= 20

    def test_popular_cn_count(self):
        from data_fetcher import POPULAR_CN_STOCKS
        assert len(POPULAR_CN_STOCKS) >= 10

    def test_popular_us_count(self):
        from data_fetcher import POPULAR_US_STOCKS
        assert len(POPULAR_US_STOCKS) >= 10

    def test_popular_hk_count(self):
        from data_fetcher import POPULAR_HK_STOCKS
        assert len(POPULAR_HK_STOCKS) >= 10

    def test_cn_no_duplicates(self):
        from data_fetcher import POPULAR_CN_STOCKS
        codes = [s['code'] for s in POPULAR_CN_STOCKS]
        assert len(codes) == len(set(codes))


# ============================================================
# TestSourcePriority
# ============================================================

class TestSourcePriority:

    def test_akshare(self, monkeypatch):
        from data_fetcher import StockDataFetcher
        df = _make_ohlcv_df(days=60, base_price=10.0)

        def mock_ak_daily(symbol, start_date, end_date, adjust):
            result = df.copy()
            result['date'] = result.index
            return result.reset_index(drop=True)

        monkeypatch.setattr('data_fetcher.AKSHARE_AVAILABLE', True)
        monkeypatch.setattr('data_fetcher.ak.stock_zh_a_daily', mock_ak_daily)
        monkeypatch.setattr('data_fetcher.StockDataFetcher._save_offline_cache',
                            lambda self, s, d: None)

        fetcher = StockDataFetcher()
        fetcher.set_preferred_source('akshare')
        result = fetcher.get_stock_data('000001', period='1y', market='CN')
        assert 'AKShare' in result.attrs.get('data_source', '')

    def test_sina(self, monkeypatch):
        from data_fetcher import StockDataFetcher
        df = _make_ohlcv_df(days=60, base_price=10.0)
        sina_json = []
        for idx, row in df.iterrows():
            sina_json.append({
                'day': idx.strftime('%Y-%m-%d'),
                'open': str(row['open']),
                'high': str(row['high']),
                'low': str(row['low']),
                'close': str(row['close']),
                'volume': str(int(row['volume'])),
            })

        def mock_get(url, headers=None, timeout=None, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.text = json.dumps(sina_json)
            return resp

        monkeypatch.setattr('data_fetcher.requests.get', mock_get)
        monkeypatch.setattr('data_fetcher.StockDataFetcher._save_offline_cache',
                            lambda self, s, d: None)

        fetcher = StockDataFetcher()
        fetcher.set_preferred_source('sina')
        result = fetcher.get_stock_data('000001', period='1y', market='CN')
        assert '新浪' in result.attrs.get('data_source', '')

    def test_yfinance(self, monkeypatch):
        from data_fetcher import StockDataFetcher
        df = _make_ohlcv_df(days=60, base_price=10.0)

        class MockTicker:
            def __init__(self, symbol):
                pass
            def history(self, period='1y', **kwargs):
                return df.copy()

        monkeypatch.setattr('data_fetcher.yf.Ticker', MockTicker)
        monkeypatch.setattr('data_fetcher.StockDataFetcher._save_offline_cache',
                            lambda self, s, d: None)

        fetcher = StockDataFetcher()
        fetcher.set_preferred_source('yfinance')
        result = fetcher.get_stock_data('000001', period='1y', market='CN')
        assert result is not None


# ============================================================
# TestConcurrencySafety
# ============================================================

class TestConcurrencySafety:

    def test_same_key_same_lock(self):
        from data_fetcher import StockDataFetcher
        fetcher = StockDataFetcher()
        l1 = fetcher._get_request_lock('test_key')
        l2 = fetcher._get_request_lock('test_key')
        assert l1 is l2

    def test_different_keys_different_locks(self):
        from data_fetcher import StockDataFetcher
        fetcher = StockDataFetcher()
        l1 = fetcher._get_request_lock('k1')
        l2 = fetcher._get_request_lock('k2')
        assert l1 is not l2
