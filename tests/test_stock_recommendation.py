"""股票推荐模块测试"""
import pytest
import pandas as pd
import numpy as np
import json


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def recommender():
    from stock_recommendation import StockRecommender
    return StockRecommender()


@pytest.fixture
def uptrend_data_60d():
    """60天上升趋势数据"""
    dates = pd.date_range('2026-01-01', periods=60, freq='B')
    close = np.linspace(9.0, 15.0, 60) + np.random.randn(60) * 0.1
    df = pd.DataFrame({
        'open': close - 0.2,
        'high': close + 0.4,
        'low': close - 0.4,
        'close': close,
        'volume': np.random.randint(1000000, 8000000, 60),
        'macd': np.linspace(-0.2, 0.8, 60),
        'macd_signal': np.linspace(-0.15, 0.5, 60),
        'macd_hist': np.linspace(-0.05, 0.3, 60),
        'rsi_6': np.linspace(40, 75, 60),
        'rsi_12': np.linspace(42, 68, 60),
        'rsi_24': np.linspace(45, 62, 60),
        'rsi': np.linspace(40, 75, 60),
        'kdj_k': np.linspace(30, 85, 60),
        'kdj_d': np.linspace(28, 78, 60),
        'kdj_j': np.linspace(35, 95, 60),
        'boll_upper': close + 1.0,
        'boll_mid': close,
        'boll_lower': close - 1.0,
        'boll_width': np.full(60, 0.08),
        'boll_percent': np.linspace(10, 90, 60),
        'ma5': close + 0.3,
        'ma10': close + 0.1,
        'ma20': close - 0.1,
        'ma60': close - 0.4,
    }, index=dates)
    return df


@pytest.fixture
def downtrend_data_60d():
    """60天下降趋势数据"""
    dates = pd.date_range('2026-01-01', periods=60, freq='B')
    close = np.linspace(15.0, 9.0, 60) + np.random.randn(60) * 0.1
    df = pd.DataFrame({
        'open': close - 0.2,
        'high': close + 0.4,
        'low': close - 0.4,
        'close': close,
        'volume': np.random.randint(1000000, 8000000, 60),
        'macd': np.linspace(0.5, -0.8, 60),
        'macd_signal': np.linspace(0.3, -0.5, 60),
        'macd_hist': np.linspace(0.2, -0.3, 60),
        'rsi_6': np.linspace(65, 20, 60),
        'rsi_12': np.linspace(60, 25, 60),
        'rsi_24': np.linspace(55, 30, 60),
        'rsi': np.linspace(65, 20, 60),
        'kdj_k': np.linspace(70, 15, 60),
        'kdj_d': np.linspace(65, 18, 60),
        'kdj_j': np.linspace(80, 8, 60),
        'boll_upper': close + 1.0,
        'boll_mid': close,
        'boll_lower': close - 1.0,
        'boll_width': np.full(60, 0.08),
        'boll_percent': np.linspace(90, 10, 60),
        'ma5': close - 0.3,
        'ma10': close - 0.1,
        'ma20': close + 0.1,
        'ma60': close + 0.4,
    }, index=dates)
    return df


def _make_mock_get_stock_data(return_data):
    """创建一个 mock get_stock_data 函数"""
    def mock_get_stock_data(symbol, period='3mo', interval='1d', market='CN'):
        return return_data
    return mock_get_stock_data


# ============================================================
# TestSectorStocks
# ============================================================

class TestSectorStocks:

    def test_four_sectors_exist(self):
        from stock_recommendation import SECTOR_STOCKS
        assert '苹果概念' in SECTOR_STOCKS
        assert '特斯拉概念' in SECTOR_STOCKS
        assert '电力' in SECTOR_STOCKS
        assert '算力租赁' in SECTOR_STOCKS

    def test_each_sector_has_min_5_stocks(self):
        from stock_recommendation import SECTOR_STOCKS
        for sector, stocks in SECTOR_STOCKS.items():
            assert len(stocks) >= 5, f"{sector} 只有 {len(stocks)} 只股票"

    def test_stocks_have_code_and_name(self):
        from stock_recommendation import SECTOR_STOCKS
        for sector, stocks in SECTOR_STOCKS.items():
            for stock in stocks:
                assert 'code' in stock
                assert 'name' in stock
                assert len(stock['code']) == 6

    def test_no_duplicate_codes(self):
        from stock_recommendation import SECTOR_STOCKS
        all_codes = []
        for stocks in SECTOR_STOCKS.values():
            for s in stocks:
                all_codes.append(s['code'])
        assert len(all_codes) == len(set(all_codes))


# ============================================================
# TestGetHotStocksCN
# ============================================================

class TestGetHotStocksCN:

    def test_returns_list(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.requests.get',
                            lambda url, headers, timeout: _mock_sina_response())
        result = recommender.get_hot_stocks_cn(limit=10)
        assert isinstance(result, list)

    def test_respects_limit(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.requests.get',
                            lambda url, headers, timeout: _mock_sina_response())
        result = recommender.get_hot_stocks_cn(limit=5)
        assert len(result) <= 5

    def test_each_stock_has_required_fields(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.requests.get',
                            lambda url, headers, timeout: _mock_sina_response())
        result = recommender.get_hot_stocks_cn(limit=5)
        if result:
            stock = result[0]
            for key in ['代码', '名称', '最新价', '涨跌幅', '热度分数']:
                assert key in stock

    def test_sorted_by_heat_score(self, recommender, monkeypatch):
        """热度分数高的排在前面"""
        monkeypatch.setattr('stock_recommendation.requests.get',
                            lambda url, headers, timeout: _mock_sina_response())
        result = recommender.get_hot_stocks_cn(limit=10)
        if len(result) >= 2:
            assert result[0]['热度分数'] >= result[-1]['热度分数']

    def test_sina_request_failure_returns_empty(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.requests.get',
                            lambda url, headers, timeout: exec('raise Exception("fail")'))
        result = recommender.get_hot_stocks_cn(limit=10)
        assert result == []

    def test_change_calculation(self, recommender, monkeypatch):
        """验证涨跌幅计算：(price - prev_close) / prev_close * 100"""
        monkeypatch.setattr('stock_recommendation.requests.get',
                            lambda url, headers, timeout: _mock_sina_response())
        result = recommender.get_hot_stocks_cn(limit=20)
        if result:
            for stock in result:
                assert -100 <= stock['涨跌幅'] <= 100  # 合理范围（非ST）


# ============================================================
# TestGetTopGainersLosersCN
# ============================================================

class TestGetTopGainersCN:

    def test_returns_list(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender._get_market_ranking',
                            lambda self, sort_asc=False, limit=10, enrich_sector=True: _make_mock_ranking(10, False))
        result = recommender.get_top_gainers_cn(limit=5)
        assert isinstance(result, list)
        assert len(result) <= 5

    def test_sorted_descending(self, recommender, monkeypatch):
        """涨幅榜应该从高到低排列"""
        monkeypatch.setattr('stock_recommendation.StockRecommender._get_market_ranking',
                            lambda self, sort_asc=False, limit=10, enrich_sector=True: _make_mock_ranking(10, False))
        result = recommender.get_top_gainers_cn(limit=10)
        if len(result) >= 2:
            assert result[0]['涨跌幅'] >= result[-1]['涨跌幅']

    def test_filters_out_zero_and_negative(self, recommender, monkeypatch):
        """涨幅榜不应包含涨跌幅≤0的股票（修复0.00%显示bug）"""
        # 构造包含0和负值的mock数据
        mock_data = [
            {'代码': '000001', '名称': '涨股1', '最新价': 15.0, '涨跌幅': 5.0, '换手率': 1.0, '成交量': 1000, '成交额': 15000},
            {'代码': '000002', '名称': '涨股2', '最新价': 12.0, '涨跌幅': 3.0, '换手率': 0.8, '成交量': 2000, '成交额': 24000},
            {'代码': '000003', '名称': '平盘股', '最新价': 10.0, '涨跌幅': 0.0, '换手率': 0.5, '成交量': 500, '成交额': 5000},
            {'代码': '000004', '名称': '涨股3', '最新价': 8.0, '涨跌幅': 1.0, '换手率': 0.3, '成交量': 800, '成交额': 6400},
            {'代码': '000005', '名称': '跌股1', '最新价': 9.0, '涨跌幅': -2.0, '换手率': 0.6, '成交量': 600, '成交额': 5400},
        ]
        monkeypatch.setattr('stock_recommendation.StockRecommender._get_market_ranking',
                            lambda self, sort_asc=False, limit=10, enrich_sector=True: mock_data)
        result = recommender.get_top_gainers_cn(limit=5)
        # 只应包含涨跌幅>0的股票
        for stock in result:
            assert stock['涨跌幅'] > 0, f"{stock['名称']} 涨跌幅={stock['涨跌幅']}，不应出现在涨幅榜"
        assert len(result) == 3  # 只有3只涨的

    def test_keeps_non_main_board_for_market_heat(self, recommender, monkeypatch):
        """热门涨幅榜用于全市场观察，不做主板过滤"""
        mock_data = [
            {'代码': '920469', '名称': '北交所股', '最新价': 8.0, '涨跌幅': 29.89, '换手率': 12.0},
            {'代码': '300210', '名称': '创业板股', '最新价': 12.0, '涨跌幅': 20.02, '换手率': 16.1},
            {'代码': '688981', '名称': '科创板股', '最新价': 50.0, '涨跌幅': 10.0, '换手率': 3.2},
            {'代码': '600519', '名称': '主板股', '最新价': 1500.0, '涨跌幅': 2.0, '换手率': 0.8},
        ]
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_market_ranking',
            lambda self, sort_asc=False, limit=10, enrich_sector=True: mock_data,
        )
        result = recommender.get_top_gainers_cn(limit=10)
        assert [stock['代码'] for stock in result] == ['920469', '300210', '688981', '600519']

    def test_all_zero_returns_empty(self, recommender, monkeypatch):
        """全部平盘时涨幅榜应为空"""
        mock_data = [
            {'代码': '000001', '名称': '平盘1', '最新价': 10.0, '涨跌幅': 0.0, '换手率': 0.1, '成交量': 100, '成交额': 1000},
            {'代码': '000002', '名称': '平盘2', '最新价': 12.0, '涨跌幅': 0.0, '换手率': 0.2, '成交量': 200, '成交额': 2400},
        ]
        monkeypatch.setattr('stock_recommendation.StockRecommender._get_market_ranking',
                            lambda self, sort_asc=False, limit=10, enrich_sector=True: mock_data)
        result = recommender.get_top_gainers_cn(limit=5)
        assert result == []


class TestGetTopLosersCN:

    def test_returns_list(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender._get_market_ranking',
                            lambda self, sort_asc=True, limit=10, enrich_sector=True: _make_mock_ranking(10, True))
        result = recommender.get_top_losers_cn(limit=5)
        assert isinstance(result, list)

    def test_calls_with_asc(self, recommender, monkeypatch):
        called_with = {}

        def mock_ranking(self, sort_asc=False, limit=10, enrich_sector=True):
            called_with['asc'] = sort_asc
            called_with['limit'] = limit
            return _make_mock_ranking(limit, sort_asc)

        monkeypatch.setattr('stock_recommendation.StockRecommender._get_market_ranking', mock_ranking)
        recommender.get_top_losers_cn(limit=8)
        assert called_with['asc'] is True
        assert called_with['limit'] == 13  # limit=8 → 请求 8+5=13

    def test_filters_out_zero_and_positive(self, recommender, monkeypatch):
        """跌幅榜不应包含涨跌幅≥0的股票"""
        mock_data = [
            {'代码': '000001', '名称': '跌股1', '最新价': 8.0, '涨跌幅': -5.0, '换手率': 1.0, '成交量': 1000, '成交额': 8000},
            {'代码': '000002', '名称': '跌股2', '最新价': 9.0, '涨跌幅': -3.0, '换手率': 0.8, '成交量': 2000, '成交额': 18000},
            {'代码': '000003', '名称': '平盘股', '最新价': 10.0, '涨跌幅': 0.0, '换手率': 0.5, '成交量': 500, '成交额': 5000},
            {'代码': '000004', '名称': '涨股1', '最新价': 11.0, '涨跌幅': 2.0, '换手率': 0.3, '成交量': 800, '成交额': 8800},
            {'代码': '000005', '名称': '跌股3', '最新价': 7.0, '涨跌幅': -1.0, '换手率': 0.6, '成交量': 600, '成交额': 4200},
        ]
        monkeypatch.setattr('stock_recommendation.StockRecommender._get_market_ranking',
                            lambda self, sort_asc=True, limit=10, enrich_sector=True: mock_data)
        result = recommender.get_top_losers_cn(limit=5)
        for stock in result:
            assert stock['涨跌幅'] < 0, f"{stock['名称']} 涨跌幅={stock['涨跌幅']}，不应出现在跌幅榜"
        assert len(result) == 3  # 只有3只跌的

    def test_keeps_non_main_board_for_market_heat(self, recommender, monkeypatch):
        """热门跌幅榜用于全市场观察，不做主板过滤"""
        mock_data = [
            {'代码': '920469', '名称': '北交所股', '最新价': 8.0, '涨跌幅': -18.0, '换手率': 12.0},
            {'代码': '300210', '名称': '创业板股', '最新价': 12.0, '涨跌幅': -10.5, '换手率': 16.1},
            {'代码': '688981', '名称': '科创板股', '最新价': 50.0, '涨跌幅': -5.2, '换手率': 3.2},
            {'代码': '600519', '名称': '主板股', '最新价': 1500.0, '涨跌幅': -2.0, '换手率': 0.8},
        ]
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_market_ranking',
            lambda self, sort_asc=True, limit=10, enrich_sector=True: mock_data,
        )
        result = recommender.get_top_losers_cn(limit=10)
        assert [stock['代码'] for stock in result] == ['920469', '300210', '688981', '600519']


# ============================================================
# TestGetHotSectorsCN
# ============================================================

class TestGetHotSectorsCN:

    def test_returns_list(self, recommender, monkeypatch):
        mock_resp = _make_mock_response(_mock_sector_html())
        monkeypatch.setattr('stock_recommendation.requests.get', lambda url, headers=None, timeout=10: mock_resp)
        result = recommender.get_hot_sectors_cn(limit=10)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_each_sector_has_fields(self, recommender, monkeypatch):
        mock_resp = _make_mock_response(_mock_sector_html())
        monkeypatch.setattr('stock_recommendation.requests.get', lambda url, headers=None, timeout=10: mock_resp)
        result = recommender.get_hot_sectors_cn(limit=5)
        if result:
            s = result[0]
            for key in ['板块', '涨跌幅', '领涨股', '上涨家数', '下跌家数']:
                assert key in s

    def test_request_failure_returns_empty(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.requests.get',
                            lambda url, headers=None, timeout=10: exec('raise Exception("fail")'))
        result = recommender.get_hot_sectors_cn()
        assert result == []


# ============================================================
# TestGetHotConceptsCN
# ============================================================

class TestGetHotConceptsCN:

    def test_returns_list(self, recommender, monkeypatch):
        mock_resp = _make_mock_response(_mock_concept_html())
        monkeypatch.setattr('stock_recommendation.requests.get', lambda url, headers=None, timeout=10: mock_resp)
        result = recommender.get_hot_concepts_cn(limit=10)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_each_concept_has_fields(self, recommender, monkeypatch):
        mock_resp = _make_mock_response(_mock_concept_html())
        monkeypatch.setattr('stock_recommendation.requests.get', lambda url, headers=None, timeout=10: mock_resp)
        result = recommender.get_hot_concepts_cn(limit=5)
        if result:
            s = result[0]
            for key in ['板块', '涨跌幅', '领涨股', '净流入(亿)']:
                assert key in s

    def test_request_failure_returns_empty(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.requests.get',
                            lambda url, headers=None, timeout=10: exec('raise Exception("fail")'))
        result = recommender.get_hot_concepts_cn()
        assert result == []


# ============================================================
# TestGetHotStocksHK
# ============================================================

class TestGetHotStocksHK:

    def test_returns_list(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.yf.Ticker', _make_mock_hk_ticker)
        result = recommender.get_hot_stocks_hk(limit=5)
        assert isinstance(result, list)

    def test_returns_empty_on_all_fail(self, recommender, monkeypatch):
        """所有 yfinance 请求失败时返回空列表"""
        def mock_ticker_fail(symbol):
            t = type('Ticker', (), {})()
            t.history = lambda period='5d': pd.DataFrame()
            t.info = {}
            return t
        monkeypatch.setattr('stock_recommendation.yf.Ticker', mock_ticker_fail)
        result = recommender.get_hot_stocks_hk(limit=5)
        # 有可能返回空列表（取决于热门股列表中是否有个别成功）
        assert isinstance(result, list)

    def test_each_stock_has_fields(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.yf.Ticker', _make_mock_hk_ticker)
        result = recommender.get_hot_stocks_hk(limit=10)
        if result:
            s = result[0]
            for key in ['代码', '名称', '最新价', '涨跌幅']:
                assert key in s


# ============================================================
# TestGetHotStocksUS
# ============================================================

class TestGetHotStocksUS:

    def test_returns_list(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.yf.Ticker', _make_mock_us_ticker)
        result = recommender.get_hot_stocks_us(limit=5)
        assert isinstance(result, list)

    def test_sorted_by_volume(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.yf.Ticker', _make_mock_us_ticker)
        result = recommender.get_hot_stocks_us(limit=10)
        if len(result) >= 2:
            assert result[0]['volume'] >= result[-1]['volume']

    def test_each_has_required_keys(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.yf.Ticker', _make_mock_us_ticker)
        result = recommender.get_hot_stocks_us(limit=5)
        if result:
            s = result[0]
            for key in ['symbol', 'name', 'price', 'change', 'volume']:
                assert key in s


# ============================================================
# TestAnalyzeStock
# ============================================================

class TestAnalyzeStock:

    def test_uptrend_scores_above_50(self, recommender, uptrend_data_60d, monkeypatch):
        _setup_analyze_mocks(monkeypatch, uptrend_data_60d, 'uptrend')
        result = recommender.analyze_stock('000001', market='CN', period='3mo')
        assert result is not None
        assert result['score'] >= 50

    def test_downtrend_scores_below_50(self, recommender, downtrend_data_60d, monkeypatch):
        _setup_analyze_mocks(monkeypatch, downtrend_data_60d, 'downtrend')
        result = recommender.analyze_stock('000001', market='CN', period='3mo')
        assert result is not None
        assert result['score'] < 50

    def test_short_data_returns_none(self, recommender, monkeypatch):
        from data_fetcher import StockDataFetcher
        short_data = pd.DataFrame({'close': [10, 11, 12]})  # 不到30条
        monkeypatch.setattr(StockDataFetcher, 'get_stock_data',
                            lambda self, symbol, period='3mo', interval='1d', market='CN': short_data)
        result = recommender.analyze_stock('000001')
        assert result is None

    def test_none_data_returns_none(self, recommender, monkeypatch):
        from data_fetcher import StockDataFetcher
        monkeypatch.setattr(StockDataFetcher, 'get_stock_data',
                            lambda self, symbol, period='3mo', interval='1d', market='CN': None)
        result = recommender.analyze_stock('000001')
        assert result is None

    def test_score_clamped_0_100(self, recommender, uptrend_data_60d, monkeypatch):
        _setup_analyze_mocks(monkeypatch, uptrend_data_60d, 'uptrend')
        result = recommender.analyze_stock('000001')
        assert 0 <= result['score'] <= 100

    def test_downtrend_score_clamped_0_100(self, recommender, downtrend_data_60d, monkeypatch):
        _setup_analyze_mocks(monkeypatch, downtrend_data_60d, 'downtrend')
        result = recommender.analyze_stock('000001')
        assert 0 <= result['score'] <= 100

    def test_result_has_all_keys(self, recommender, uptrend_data_60d, monkeypatch):
        _setup_analyze_mocks(monkeypatch, uptrend_data_60d, 'uptrend')
        result = recommender.analyze_stock('000001')
        for key in ['symbol', 'score', 'rating', 'signals', 'latest_price', 'indicators']:
            assert key in result

    def test_indicators_have_all_values(self, recommender, uptrend_data_60d, monkeypatch):
        _setup_analyze_mocks(monkeypatch, uptrend_data_60d, 'uptrend')
        result = recommender.analyze_stock('000001')
        ind = result['indicators']
        for key in ['macd', 'macd_signal', 'rsi', 'kdj_k', 'kdj_d', 'kdj_j',
                     'boll_upper', 'boll_mid', 'boll_lower']:
            assert key in ind

    def test_error_signals_returns_none(self, recommender, uptrend_data_60d, monkeypatch):
        _setup_analyze_mocks(monkeypatch, uptrend_data_60d, 'error')
        result = recommender.analyze_stock('000001')
        assert result is None

    def test_uptrend_rating_is_bullish(self, recommender, uptrend_data_60d, monkeypatch):
        _setup_analyze_mocks(monkeypatch, uptrend_data_60d, 'strong_uptrend')
        result = recommender.analyze_stock('000001')
        # 强上升趋势应该是偏多信号
        assert '偏多' in result['rating']


# ============================================================
# TestAnalyzeShortTerm
# ============================================================

class TestAnalyzeShortTerm:

    def test_returns_none_for_short_data(self, recommender, monkeypatch):
        from data_fetcher import StockDataFetcher
        short_df = pd.DataFrame({
            'close': [10, 11], 'rsi': [50, 50],
        })
        monkeypatch.setattr(StockDataFetcher, 'get_stock_data',
                            lambda self, symbol, period='1mo', interval='1d', market='CN': short_df)
        result = recommender._analyze_short_term('000001')
        assert result is None

    def test_returns_none_for_none_data(self, recommender, monkeypatch):
        from data_fetcher import StockDataFetcher
        monkeypatch.setattr(StockDataFetcher, 'get_stock_data',
                            lambda self, symbol, period='1mo', interval='1d', market='CN': None)
        result = recommender._analyze_short_term('000001')
        assert result is None

    def test_result_has_strategy_field(self, recommender, uptrend_data_60d, monkeypatch):
        _setup_short_term_mocks(monkeypatch, uptrend_data_60d, 'uptrend')
        result = recommender._analyze_short_term('000001')
        assert result is not None
        assert result['strategy'] == '短线'

    def test_score_clamped_0_100(self, recommender, uptrend_data_60d, monkeypatch):
        _setup_short_term_mocks(monkeypatch, uptrend_data_60d, 'uptrend')
        result = recommender._analyze_short_term('000001')
        assert 0 <= result['score'] <= 100

    def test_volatility_bonus(self, recommender, uptrend_data_60d, monkeypatch):
        """波动率适中的股票应该有加分（间接验证，不崩溃即可）"""
        _setup_short_term_mocks(monkeypatch, uptrend_data_60d, 'uptrend')
        result = recommender._analyze_short_term('000001')
        assert result is not None


# ============================================================
# TestGetRecommendedStocksCN
# ============================================================

class TestGetRecommendedStocksCN:

    def test_uses_main_board_pool_before_limit(self, recommender, monkeypatch):
        pool = [
            {'code': '300750', 'name': '宁德时代'},
            {'code': '688981', 'name': '中芯国际'},
            {'code': '835185', 'name': '贝特瑞'},
            {'code': '000001', 'name': '平安银行'},
            {'code': '600519', 'name': '贵州茅台'},
        ]
        analyzed = []
        monkeypatch.setattr('stock_recommendation.get_popular_cn_stocks', lambda: pool)

        def mock_analyze(self, code, market='CN', period='3mo'):
            analyzed.append(code)
            return _mock_analysis(code)

        monkeypatch.setattr('stock_recommendation.StockRecommender.analyze_stock', mock_analyze)
        result = recommender.get_recommended_stocks_cn(num_stocks=5)
        assert analyzed == ['000001', '600519']
        assert [r['symbol'] for r in result] == ['600519', '000001']

    def test_returns_list(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender.analyze_stock',
                            lambda self, code, market='CN', period='3mo': _mock_analysis(code))
        result = recommender.get_recommended_stocks_cn(num_stocks=5)
        assert isinstance(result, list)

    def test_only_score_at_least_60(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender.analyze_stock',
                            lambda self, code, market='CN', period='3mo': _mock_analysis(code))
        result = recommender.get_recommended_stocks_cn(num_stocks=10)
        for r in result:
            assert r['score'] >= 60

    def test_sorted_descending(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender.analyze_stock',
                            lambda self, code, market='CN', period='3mo': _mock_analysis(code))
        result = recommender.get_recommended_stocks_cn(num_stocks=5)
        if len(result) >= 2:
            assert result[0]['score'] >= result[-1]['score']

    def test_includes_name_field(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender.analyze_stock',
                            lambda self, code, market='CN', period='3mo': _mock_analysis(code))
        result = recommender.get_recommended_stocks_cn(num_stocks=5)
        if result:
            assert 'name' in result[0]


# ============================================================
# TestGetShortTermRecommendations
# ============================================================

class TestGetShortTermRecommendations:

    def test_filters_non_main_board(self, recommender, monkeypatch):
        pool = [
            {'code': '300750', 'name': '宁德时代'},
            {'code': '688981', 'name': '中芯国际'},
            {'code': '000001', 'name': '平安银行'},
            {'code': '600519', 'name': '贵州茅台'},
        ]
        analyzed = []
        monkeypatch.setattr('stock_recommendation.get_popular_cn_stocks', lambda: pool)

        def mock_short(self, code, market='CN'):
            analyzed.append(code)
            return _mock_short_analysis(code)

        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_short_term', mock_short)
        result = recommender.get_short_term_recommendations(num_stocks=5)
        assert analyzed == ['000001', '600519']
        assert all(not r['symbol'].startswith(('300', '688', '8')) for r in result)

    def test_returns_list(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_short_term',
                            lambda self, code, market='CN': _mock_short_analysis(code))
        result = recommender.get_short_term_recommendations(num_stocks=5)
        assert isinstance(result, list)

    def test_sorted_descending(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_short_term',
                            lambda self, code, market='CN': _mock_short_analysis(code))
        result = recommender.get_short_term_recommendations(num_stocks=5)
        if len(result) >= 2:
            assert result[0]['score'] >= result[-1]['score']


# ============================================================
# TestGetSectorShortTerm
# ============================================================

class TestGetLongTermRecommendations:

    def test_filters_non_main_board(self, recommender, monkeypatch):
        pool = [
            {'code': '300750', 'name': '宁德时代'},
            {'code': '688981', 'name': '中芯国际'},
            {'code': '000001', 'name': '平安银行'},
            {'code': '600519', 'name': '贵州茅台'},
        ]
        analyzed = []
        monkeypatch.setattr('stock_recommendation.get_popular_cn_stocks', lambda: pool)

        def mock_long(self, code, market='CN'):
            analyzed.append(code)
            return _mock_long_analysis(code)

        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_long_term', mock_long)
        result = recommender.get_long_term_recommendations(num_stocks=5)
        assert analyzed == ['000001', '600519']
        assert all(not r['symbol'].startswith(('300', '688', '8')) for r in result)

    def test_returns_list(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_long_term',
                            lambda self, code, market='CN': _mock_long_analysis(code))
        result = recommender.get_long_term_recommendations(num_stocks=5)
        assert isinstance(result, list)

    def test_sorted_descending(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_long_term',
                            lambda self, code, market='CN': _mock_long_analysis(code))
        result = recommender.get_long_term_recommendations(num_stocks=5)
        if len(result) >= 2:
            assert result[0]['score'] >= result[-1]['score']

    def test_includes_name_field(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_long_term',
                            lambda self, code, market='CN': _mock_long_analysis(code))
        result = recommender.get_long_term_recommendations(num_stocks=5)
        if result:
            assert 'name' in result[0]


class TestGetSectorShortTerm:

    def test_invalid_sector_returns_empty(self, recommender):
        result = recommender.get_sector_short_term_recommendations('不存在的板块')
        assert result == []

    def test_valid_sector_returns_list(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_short_term',
                            lambda self, code, market='CN': _mock_short_analysis(code))
        result = recommender.get_sector_short_term_recommendations('苹果概念', num_stocks=3)
        assert isinstance(result, list)

    def test_includes_sector_name(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_short_term',
                            lambda self, code, market='CN': _mock_short_analysis(code))
        result = recommender.get_sector_short_term_recommendations('电力', num_stocks=5)
        if result:
            assert result[0]['sector'] == '电力'

    def test_filters_non_main_board_sector_stocks(self, recommender, monkeypatch):
        sector_pool = {
            '测试板块': [
                {'code': '300750', 'name': '宁德时代'},
                {'code': '688981', 'name': '中芯国际'},
                {'code': '000001', 'name': '平安银行'},
                {'code': '600519', 'name': '贵州茅台'},
            ]
        }
        analyzed = []
        monkeypatch.setattr('stock_recommendation.SECTOR_STOCKS', sector_pool)

        def mock_short(self, code, market='CN'):
            analyzed.append(code)
            return _mock_short_analysis(code)

        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_short_term', mock_short)
        result = recommender.get_sector_short_term_recommendations('测试板块', num_stocks=5)
        assert analyzed == ['000001', '600519']
        assert all(not r['symbol'].startswith(('300', '688', '8')) for r in result)


# ============================================================
# TestMarketRanking
# ============================================================

class TestMarketRanking:

    def test_returns_list(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.requests.get',
                            lambda url, params, headers, timeout: _mock_ranking_resp())
        result = recommender._get_market_ranking(sort_asc=False, limit=5)
        assert isinstance(result, list)

    def test_limit_respected(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.requests.get',
                            lambda url, params, headers, timeout: _mock_ranking_resp())
        result = recommender._get_market_ranking(sort_asc=False, limit=5)
        assert len(result) <= 5

    def test_failure_returns_empty(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.requests.get',
                            lambda url, params, headers, timeout: exec('raise Exception("fail")'))
        result = recommender._get_market_ranking()
        assert result == []

    def test_each_item_has_fields(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.requests.get',
                            lambda url, params, headers, timeout: _mock_ranking_resp())
        result = recommender._get_market_ranking(limit=3)
        if result:
            item = result[0]
            for key in ['代码', '名称', '最新价', '涨跌幅']:
                assert key in item

    def test_ths_ranking_parser(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.requests.get',
                            lambda url, params, headers, timeout: _make_mock_response(_mock_ths_ranking_html()))
        result = recommender._get_market_ranking_ths(sort_asc=False, limit=2)

        assert result[0]['代码'] == '920469'
        assert result[0]['名称'] == '富恒新材'
        assert result[0]['涨跌幅'] == 29.89
        assert result[0]['换手率'] == 14.96

    def test_falls_back_to_sina_when_ths_blocked(self, recommender, monkeypatch):
        def mock_get(url, params, headers, timeout):
            if '10jqka' in url:
                return _make_mock_response('<html>blocked</html>', status_code=401)
            return _mock_ranking_resp()

        monkeypatch.setattr('stock_recommendation.requests.get', mock_get)
        result = recommender._get_market_ranking(sort_asc=False, limit=3)

        assert result
        assert result[0]['代码'] == '000001'


# ============================================================
# Helpers
# ============================================================

def _mock_sina_response():
    """构造模拟的新浪批量行情响应"""
    class MockResponse:
        status_code = 200
        text = ''
    resp = MockResponse()
    lines = []
    from data_fetcher import get_popular_cn_stocks
    for i, stock in enumerate(get_popular_cn_stocks()[:30]):
        code = stock['code']
        prefix = 'sh' if code.startswith(('6', '68')) else 'sz'
        price = 10 + i * 0.5
        prev_close = price - 0.2
        # 新浪格式: 名称,今开,昨收,当前价,最高,最低,...,成交量,...
        fields = [
            stock['name'],  # 0 名称
            str(price - 0.1),  # 1 今开
            str(prev_close),  # 2 昨收
            str(price),  # 3 当前价
            str(price + 0.3),  # 4 最高
            str(price - 0.3),  # 5 最低
            str(price),  # 6 竞买价
            str(price),  # 7 竞卖价
            str(1000000 + i * 100000),  # 8 成交量
            str((1000000 + i * 100000) * price),  # 9 成交额
            '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '',
            str(price),
            str(prev_close),  # 32 change (unreliable)
        ]
        line = f'hq_str_{prefix}{code}="{",".join(fields)}"'
        lines.append(line)
    resp.text = '\n'.join(lines)
    return resp


def _make_mock_ranking(count, asc=False):
    results = []
    for i in range(count):
        change = (-5 + i * 1.2) if asc else (10 - i * 0.8)
        results.append({
            '代码': f'00000{i+1}',
            '名称': f'股票{i+1}',
            '最新价': round(10 + i * 0.5, 2),
            '涨跌幅': round(change, 2),
            '换手率': round(1.5 + i * 0.3, 2),
            '成交量': 5000000 + i * 100000,
            '成交额': 50000000 + i * 1000000,
        })
    return results


def _mock_ranking_resp():
    class MockResponse:
        status_code = 200

        @staticmethod
        def json():
            return [
                {'code': '000001', 'name': '平安银行', 'trade': 12.5, 'changepercent': 3.5,
                 'turnoverratio': 1.2, 'volume': 50000000, 'amount': 600000000},
                {'code': '000002', 'name': '万科A', 'trade': 15.3, 'changepercent': -2.1,
                 'turnoverratio': 0.8, 'volume': 30000000, 'amount': 450000000},
                {'code': '000003', 'name': '测试股', 'trade': 8.9, 'changepercent': 5.2,
                 'turnoverratio': 2.1, 'volume': 70000000, 'amount': 620000000},
            ]
    return MockResponse()


def _mock_ths_ranking_html():
    return '''
    <html><body><table class="m-table m-pager-table">
    <tr><th>序号</th><th>代码</th><th>名称</th><th>现价</th><th>涨跌幅</th><th>涨跌</th><th>涨速</th><th>换手</th><th>换手率</th></tr>
    <tr><td>1</td><td>920469</td><td>富恒新材</td><td>8.17</td><td>29.89</td><td>1.88</td><td>0.00</td><td>--</td><td>14.96</td></tr>
    <tr><td>2</td><td>300210</td><td>森远股份</td><td>12.05</td><td>20.02</td><td>2.01</td><td>0.00</td><td>--</td><td>16.11</td></tr>
    </table></body></html>
    '''


class MockResponse:
    def __init__(self, html, status_code=200, encoding='utf-8'):
        self.text = html
        self.status_code = status_code
        self.encoding = encoding


def _make_mock_response(html, status_code=200):
    """创建一个模拟的 requests.Response"""
    return MockResponse(html, status_code)


def _mock_sector_html():
    """构建模拟同花顺行业板块页面HTML"""
    rows_html = ""
    data = [
        ('半导体', '3.5', '中芯国际', '55.0', '7.5', '45', '5', '1250', '85'),
        ('新能源汽车', '2.8', '比亚迪', '280.0', '5.2', '38', '8', '980', '52'),
        ('人工智能', '2.1', '科大讯飞', '52.0', '4.8', '32', '12', '750', '30'),
        ('医药', '-1.2', '恒瑞医药', '42.0', '0.8', '15', '28', '420', '-45'),
        ('白酒', '0.5', '贵州茅台', '1800.0', '1.2', '10', '8', '350', '18'),
    ]
    for i, (name, change, lead, lead_price, lead_change, up, down, vol, net) in enumerate(data, 1):
        rows_html += f'<tr><td>{i}</td><td>{name}</td><td>{change}</td><td>1000</td><td>{vol}</td><td>{net}</td><td>{up}</td><td>{down}</td><td>10.0</td><td>{lead}</td><td>{lead_price}</td><td>{lead_change}</td></tr>'
    return f'<html><body><table class="m-table"><tr><th>序号</th><th>板块</th><th>涨跌幅(%)</th><th>总成交量</th><th>总成交额</th><th>净流入</th><th>上涨家数</th><th>下跌家数</th><th>均价</th><th>领涨股</th><th>领涨股-最新价</th><th>领涨股-涨跌幅</th></tr>{rows_html}</table></body></html>'


def _mock_concept_html():
    """构建模拟同花顺概念板块资金流向页面HTML"""
    rows_html = ""
    data = [
        ('F5G概念', '3.13', '仕佳为', '240.40', '20.00', '28.61'),
        ('算力', '3.06', '焊湔工程', '41.56', '20.01', '38.34'),
        ('科创板新股', '2.81', '天铭科技', '85.64', '19.99', '-8.86'),
    ]
    for i, (name, change, lead, lead_price, lead_change, net) in enumerate(data, 1):
        rows_html += f'<tr><td>{i}</td><td>{name}</td><td>1000</td><td>{change}%</td><td>100</td><td>100</td><td>{net}</td><td>30</td><td>{lead}</td><td>{lead_change}%</td><td>{lead_price}</td></tr>'
    return f'<html><body><table><tr><th>序号</th><th>行业</th><th>行业指数</th><th>涨跌幅</th><th>主力资金(亿)</th><th>最大资金(亿)</th><th>净流入(亿)</th><th>公司数目</th><th>领涨股</th><th>涨跌幅</th><th>当前价(元)</th></tr>{rows_html}</table></body></html>'


def _make_mock_hk_ticker(symbol):
    class MockTicker:
        def __init__(self, sym):
            self._sym = sym

        @property
        def info(self):
            return {'shortName': self._sym.replace('.HK', '')}

        def history(self, period='5d'):
            dates = pd.date_range('2026-04-01', periods=5)
            return pd.DataFrame({
                'Open': [50, 51, 52, 51, 53],
                'High': [52, 53, 54, 53, 54],
                'Low': [49, 50, 51, 50, 52],
                'Close': [51, 52, 53, 52, 54],
                'Volume': [1000000, 1200000, 1100000, 1300000, 1500000],
            }, index=dates)
    return MockTicker(symbol)


def _make_mock_us_ticker(symbol):
    class MockTicker:
        def __init__(self, sym):
            self._sym = sym

        @property
        def info(self):
            return {'shortName': symbol, 'marketCap': 1000000000000}

        def history(self, period='5d'):
            dates = pd.date_range('2026-04-01', periods=5)
            return pd.DataFrame({
                'Open': [150, 152, 153, 151, 155],
                'High': [155, 156, 157, 155, 158],
                'Low': [148, 150, 151, 149, 153],
                'Close': [152, 154, 155, 152, 156],
                'Volume': [5000000, 5500000, 6000000, 5800000, 6200000],
            }, index=dates)
    return MockTicker(symbol)


def _setup_analyze_mocks(monkeypatch, data, signal_type):
    """设置 analyze_stock 所需的 mock"""
    from data_fetcher import StockDataFetcher
    from technical_indicators import TechnicalIndicators

    # Mock get_stock_data
    monkeypatch.setattr(StockDataFetcher, 'get_stock_data',
                        lambda self, symbol, period='3mo', interval='1d', market='CN': data)

    # Mock calculate_all (return as-is since data already has indicators)
    monkeypatch.setattr(TechnicalIndicators, 'calculate_all', lambda d: d)

    # Mock get_signals
    if signal_type == 'uptrend':
        signals = {
            'macd': 'MACD金叉，偏多',
            'rsi': 'RSI 58，中性',
            'kdj': 'KDJ向上，偏多',
            'boll': '价格在中轨附近，偏多',
            'recommendation': '偏多信号',
        }
    elif signal_type == 'strong_uptrend':
        signals = {
            'macd': 'MACD多头强势，金叉',
            'rsi': 'RSI 25，超卖',
            'kdj': 'KDJ金叉，强势，超卖反弹',
            'boll': '下轨反弹',
            'recommendation': '偏多信号',
        }
    elif signal_type == 'downtrend':
        signals = {
            'macd': 'MACD死叉，偏空',
            'rsi': 'RSI 72，超买',
            'kdj': 'KDJ死叉，强势，超买',
            'boll': '上轨回调',
            'recommendation': '偏空信号',
        }
    elif signal_type == 'error':
        signals = {'error': 'something went wrong'}
    else:
        signals = {
            'macd': 'MACD多头，偏多',
            'rsi': 'RSI 45，中性',
            'kdj': 'KDJ金叉，偏多',
            'boll': '中轨附近',
            'recommendation': '观望',
        }
    monkeypatch.setattr(TechnicalIndicators, 'get_signals', lambda d: signals)


def _setup_short_term_mocks(monkeypatch, data, signal_type):
    """设置 _analyze_short_term 所需的 mock"""
    from data_fetcher import StockDataFetcher
    from technical_indicators import TechnicalIndicators

    monkeypatch.setattr(StockDataFetcher, 'get_stock_data',
                        lambda self, symbol, period='1mo', interval='1d', market='CN': data)
    monkeypatch.setattr(TechnicalIndicators, 'calculate_all', lambda d: d)
    monkeypatch.setattr(TechnicalIndicators, 'get_signals', lambda d: {
        'macd': 'MACD金叉，偏多',
        'rsi': 'RSI 45，中性',
        'kdj': 'KDJ向上，偏多',
        'boll': '中轨附近，偏多',
        'recommendation': '偏多信号',
    })


def _mock_analysis(code):
    """模拟 analyze_stock 返回（用于推荐列表测试）"""
    code_int = int(code)
    score = 50 + (code_int % 50)
    if score < 60:
        score = 62  # 确保至少60分才能进入推荐
    return {
        'symbol': code,
        'score': score,
        'rating': '偏多信号' if score >= 65 else '观望',
        'signals': {},
        'latest_price': 10.0 + code_int * 0.1,
        'indicators': {},
    }


def _mock_short_analysis(code):
    code_int = int(code)
    return {
        'symbol': code,
        'score': 55 + (code_int % 45),
        'rating': '偏多信号',
        'signals': {},
        'latest_price': 10.0 + code_int * 0.1,
        'change_pct': round(1.5 + code_int * 0.1, 2),
        'strategy': '短线',
        'indicators': {},
    }


def _mock_long_analysis(code):
    code_int = int(code)
    return {
        'symbol': code,
        'score': 50 + (code_int % 40),
        'rating': '偏多信号',
        'signals': {},
        'latest_price': 10.0 + code_int * 0.1,
        'change_pct': round(0.8 + code_int * 0.05, 2),
        'strategy': '长线',
        'indicators': {},
    }


def _setup_long_term_mocks(monkeypatch, data, signal_type):
    """设置 _analyze_long_term 所需的 mock"""
    from data_fetcher import StockDataFetcher
    from technical_indicators import TechnicalIndicators

    monkeypatch.setattr(StockDataFetcher, 'get_stock_data',
                        lambda self, symbol, period='1y', interval='1d', market='CN': data)
    monkeypatch.setattr(TechnicalIndicators, 'calculate_all', lambda d: d)
    if signal_type == 'uptrend':
        signals = {
            'macd': 'MACD金叉，偏多',
            'rsi': 'RSI 55，中性',
            'kdj': 'KDJ向上，偏多',
            'boll': '中轨附近，偏多',
            'recommendation': '偏多信号',
        }
    else:
        signals = {
            'macd': 'MACD死叉，偏空',
            'rsi': 'RSI 60，偏空',
            'kdj': 'KDJ向下，偏空',
            'boll': '上轨回调',
            'recommendation': '偏空信号',
        }
    monkeypatch.setattr(TechnicalIndicators, 'get_signals', lambda d: signals)


# ============================================================
# TestGetTopGainersLosersHK
# ============================================================

class TestGetTopGainersLosersHK:

    def test_gainers_returns_positive_only(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.yf.Ticker', _make_mock_hk_ticker)
        result = recommender.get_top_gainers_hk(limit=5)
        assert isinstance(result, list)
        for s in result:
            assert s['涨跌幅'] > 0

    def test_losers_returns_negative_only(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.yf.Ticker', _make_mock_hk_ticker)
        result = recommender.get_top_losers_hk(limit=5)
        assert isinstance(result, list)
        for s in result:
            assert s['涨跌幅'] < 0

    def test_gainers_obey_limit(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.yf.Ticker', _make_mock_hk_ticker)
        result = recommender.get_top_gainers_hk(limit=3)
        assert len(result) <= 3

    def test_losers_obey_limit(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.yf.Ticker', _make_mock_hk_ticker)
        result = recommender.get_top_losers_hk(limit=3)
        assert len(result) <= 3


# ============================================================
# TestGetTopGainersLosersUS
# ============================================================

class TestGetTopGainersLosersUS:

    def test_gainers_returns_positive_only(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.yf.Ticker', _make_mock_us_ticker)
        result = recommender.get_top_gainers_us(limit=5)
        assert isinstance(result, list)
        for s in result:
            assert s['change'] > 0

    def test_losers_returns_negative_only(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.yf.Ticker', _make_mock_us_ticker)
        result = recommender.get_top_losers_us(limit=5)
        assert isinstance(result, list)
        for s in result:
            assert s['change'] < 0

    def test_gainers_obey_limit(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.yf.Ticker', _make_mock_us_ticker)
        result = recommender.get_top_gainers_us(limit=3)
        assert len(result) <= 3


# ============================================================
# TestAnalyzeLongTerm
# ============================================================

class TestAnalyzeLongTerm:

    def test_returns_none_for_short_data(self, recommender, monkeypatch):
        from data_fetcher import StockDataFetcher
        short_df = pd.DataFrame({
            'close': [10, 11], 'rsi': [50, 50],
        })
        monkeypatch.setattr(StockDataFetcher, 'get_stock_data',
                            lambda self, symbol, period='1y', interval='1d', market='CN': short_df)
        result = recommender._analyze_long_term('000001')
        assert result is None

    def test_returns_none_for_none_data(self, recommender, monkeypatch):
        from data_fetcher import StockDataFetcher
        monkeypatch.setattr(StockDataFetcher, 'get_stock_data',
                            lambda self, symbol, period='1y', interval='1d', market='CN': None)
        result = recommender._analyze_long_term('000001')
        assert result is None

    def test_result_has_strategy_field(self, recommender, uptrend_data_60d, monkeypatch):
        _setup_long_term_mocks(monkeypatch, uptrend_data_60d, 'uptrend')
        result = recommender._analyze_long_term('000001')
        assert result is not None
        assert result['strategy'] == '长线'

    def test_score_clamped_0_100(self, recommender, uptrend_data_60d, monkeypatch):
        _setup_long_term_mocks(monkeypatch, uptrend_data_60d, 'uptrend')
        result = recommender._analyze_long_term('000001')
        assert 0 <= result['score'] <= 100

    def test_uptrend_scores_higher_than_downtrend(self, recommender, uptrend_data_60d, downtrend_data_60d, monkeypatch):
        """上升趋势长线评分应高于下降趋势"""
        _setup_long_term_mocks(monkeypatch, uptrend_data_60d, 'uptrend')
        up_result = recommender._analyze_long_term('000001')
        up_score = up_result['score']

        _setup_long_term_mocks(monkeypatch, downtrend_data_60d, 'downtrend')
        down_result = recommender._analyze_long_term('000001')
        down_score = down_result['score']

        assert up_score > down_score, f"上升评分{up_score} 应 > 下降评分{down_score}"

    def test_change_pct_field_present(self, recommender, uptrend_data_60d, monkeypatch):
        _setup_long_term_mocks(monkeypatch, uptrend_data_60d, 'uptrend')
        result = recommender._analyze_long_term('000001')
        assert 'change_pct' in result
        assert isinstance(result['change_pct'], (int, float))


# ============================================================
# TestGetSectorLongTerm
# ============================================================

class TestGetSectorLongTerm:

    def test_invalid_sector_returns_empty(self, recommender):
        result = recommender.get_sector_long_term_recommendations('不存在的板块')
        assert result == []

    def test_valid_sector_returns_list(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_long_term',
                            lambda self, code, market='CN': _mock_long_analysis(code))
        result = recommender.get_sector_long_term_recommendations('苹果概念', num_stocks=3)
        assert isinstance(result, list)

    def test_includes_sector_name(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_long_term',
                            lambda self, code, market='CN': _mock_long_analysis(code))
        result = recommender.get_sector_long_term_recommendations('电力', num_stocks=5)
        if result:
            assert result[0]['sector'] == '电力'

    def test_respects_num_stocks(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_long_term',
                            lambda self, code, market='CN': _mock_long_analysis(code))
        result = recommender.get_sector_long_term_recommendations('特斯拉概念', num_stocks=2)
        assert len(result) <= 2

    def test_filters_non_main_board_sector_stocks(self, recommender, monkeypatch):
        sector_pool = {
            '测试板块': [
                {'code': '300750', 'name': '宁德时代'},
                {'code': '688981', 'name': '中芯国际'},
                {'code': '000001', 'name': '平安银行'},
                {'code': '600519', 'name': '贵州茅台'},
            ]
        }
        analyzed = []
        monkeypatch.setattr('stock_recommendation.SECTOR_STOCKS', sector_pool)

        def mock_long(self, code, market='CN'):
            analyzed.append(code)
            return _mock_long_analysis(code)

        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_long_term', mock_long)
        result = recommender.get_sector_long_term_recommendations('测试板块', num_stocks=5)
        assert analyzed == ['000001', '600519']
        assert all(not r['symbol'].startswith(('300', '688', '8')) for r in result)


# ============================================================
# TestGetAllSectorRecommendations
# ============================================================

class TestGetAllSectorRecommendations:

    def test_returns_dict_with_4_sectors(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_short_term',
                            lambda self, code, market='CN': _mock_short_analysis(code))
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_long_term',
                            lambda self, code, market='CN': _mock_long_analysis(code))
        result = recommender.get_all_sector_recommendations()
        assert isinstance(result, dict)
        for sector in ['苹果概念', '特斯拉概念', '电力', '算力租赁']:
            assert sector in result

    def test_each_sector_has_short_and_long(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_short_term',
                            lambda self, code, market='CN': _mock_short_analysis(code))
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_long_term',
                            lambda self, code, market='CN': _mock_long_analysis(code))
        result = recommender.get_all_sector_recommendations()
        for sector, data in result.items():
            assert '短线' in data
            assert '长线' in data
            assert isinstance(data['短线'], list)
            assert isinstance(data['长线'], list)

    def test_stocks_have_strategy_field(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_short_term',
                            lambda self, code, market='CN': _mock_short_analysis(code))
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_long_term',
                            lambda self, code, market='CN': _mock_long_analysis(code))
        result = recommender.get_all_sector_recommendations()
        for sector, data in result.items():
            for s in data['短线']:
                assert s['strategy'] == '短线'
            for s in data['长线']:
                assert s['strategy'] == '长线'
