"""股票推荐模块测试"""
import pytest
import pandas as pd
import numpy as np
import json


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def recommender(tmp_path):
    from data.cache import JsonFileCache
    from stock_recommendation import StockRecommender
    item = StockRecommender()
    item._board_ranking_cache = JsonFileCache("board_rankings_test", 86400, cache_dir=tmp_path)
    return item


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

    def test_sectors_exist(self):
        from stock_recommendation import SECTOR_STOCKS
        assert '苹果概念' in SECTOR_STOCKS
        assert '特斯拉概念' in SECTOR_STOCKS

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

    def test_ths_hotlist_sector_board_used_before_wencai(self, recommender, monkeypatch, tmp_path):
        from data.cache import JsonFileCache

        recommender._board_ranking_cache = JsonFileCache("board_rankings_test_ths_hotlist_sectors", 86400, cache_dir=tmp_path)
        monkeypatch.setattr(
            recommender,
            "_get_hot_sectors_ths_hotlist",
            lambda limit=30: [{"板块": "半导体", "热度": 20734.5, "涨跌幅": 2.29, "数据源": "同花顺热门行业板块"}],
        )
        monkeypatch.setattr(
            recommender,
            "_get_hot_sectors_wencai",
            lambda limit=30: exec('raise AssertionError("wencai source should not run")'),
        )

        result = recommender.get_hot_sectors_cn(limit=5)

        assert result[0]["板块"] == "半导体"
        assert result[0]["热度"] == 20734.5
        assert result[0]["数据源"] == "同花顺热门行业板块"

    def test_wencai_sector_board_used_before_public_pages(self, recommender, monkeypatch, tmp_path):
        from data.cache import JsonFileCache

        recommender._board_ranking_cache = JsonFileCache("board_rankings_test_wencai_sectors", 86400, cache_dir=tmp_path)
        monkeypatch.setenv("WENCAI_COOKIE", "test-cookie")
        monkeypatch.setattr(recommender, "_get_hot_sectors_ths_hotlist", lambda limit=30: [])

        def fake_wencai(query, source, limit=30):
            assert "行业板块" in query
            return [{"板块": "机器人", "涨跌幅": 4.2, "领涨股": "测试股份", "数据源": source}]

        monkeypatch.setattr(recommender, "_get_hot_boards_wencai", fake_wencai)
        monkeypatch.setattr(
            'stock_recommendation.hot_stocks._SINA_SESSION.get',
            lambda *args, **kwargs: exec('raise AssertionError("public source should not run")'),
        )

        result = recommender.get_hot_sectors_cn(limit=5)

        assert result[0]["板块"] == "机器人"
        assert result[0]["数据源"] == "问财行业热榜"

    def test_wencai_board_skips_without_cookie(self, recommender, monkeypatch):
        monkeypatch.delenv("WENCAI_COOKIE", raising=False)
        monkeypatch.delenv("IWENCAI_COOKIE", raising=False)

        assert recommender._get_hot_sectors_wencai(limit=5) == []

    def test_normalize_wencai_board_ranking(self, recommender):
        df = pd.DataFrame([
            {"板块名称": "PCB概念", "涨跌幅": "3.5%", "领涨股": "胜宏科技", "主力净流入": "2.1亿"},
            {"板块名称": "机器人", "涨跌幅": "4.2%", "领涨股": "测试股份", "成交额": "100000000"},
        ])

        result = recommender._normalize_wencai_board_ranking(df, source="问财概念热榜")

        assert [row["板块"] for row in result] == ["机器人", "PCB概念"]
        assert result[0]["涨跌幅"] == 4.2
        assert result[0]["数据源"] == "问财概念热榜"

    def test_normalize_wencai_board_ranking_with_index_dynamic_columns(self, recommender):
        df = pd.DataFrame([
            {
                "指数简称": "牙科医疗",
                "指数@涨跌幅:前复权[20260618]": 3.1694,
                "指数@成交额[20260618]": 27824566000,
            },
            {
                "指数简称": "稀土",
                "指数@涨跌幅:前复权[20260618]": 6.7269,
                "指数@成交额[20260618]": 112000000000,
            },
        ])

        result = recommender._normalize_wencai_board_ranking(df, source="问财行业热榜")

        assert [row["板块"] for row in result] == ["稀土", "牙科医疗"]
        assert result[0]["涨跌幅"] == 6.73
        assert result[0]["总成交额(亿)"] == 1120

    def test_normalize_ths_hot_plate_item(self, recommender):
        result = recommender._normalize_ths_hot_plate_item(
            {
                "name": "PCB概念",
                "rise_and_fall": 1.4188,
                "rate": "24803.5",
                "order": 2,
                "hot_rank_chg": 1,
                "code": "885959",
                "market_id": 48,
                "tag": "11家涨停",
            },
            category="概念",
            source="同花顺热门概念板块",
        )

        assert result["板块"] == "PCB概念"
        assert result["涨跌幅"] == 1.42
        assert result["热度"] == 24803.5
        assert result["排名"] == 2
        assert result["类别"] == "概念"

    def test_returns_list(self, recommender, monkeypatch):
        mock_resp = _make_mock_response(_mock_sector_html())
        monkeypatch.setattr(
            'stock_recommendation.hot_stocks._SINA_SESSION.get',
            lambda url, headers=None, timeout=4: mock_resp,
        )
        result = recommender.get_hot_sectors_cn(limit=10)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_each_sector_has_fields(self, recommender, monkeypatch):
        mock_resp = _make_mock_response(_mock_sector_html())
        monkeypatch.setattr(
            'stock_recommendation.hot_stocks._SINA_SESSION.get',
            lambda url, headers=None, timeout=4: mock_resp,
        )
        result = recommender.get_hot_sectors_cn(limit=5)
        if result:
            s = result[0]
            for key in ['板块', '涨跌幅', '领涨股', '上涨家数', '下跌家数']:
                assert key in s

    def test_request_failure_marks_unavailable_without_cache(self, recommender, monkeypatch, tmp_path):
        from data.cache import JsonFileCache

        recommender._board_ranking_cache = JsonFileCache("board_rankings_test_empty_sectors", 1, cache_dir=tmp_path)
        monkeypatch.setattr(
            'stock_recommendation.hot_stocks._SINA_SESSION.get',
            lambda *args, **kwargs: exec('raise Exception("fail")'),
        )
        monkeypatch.setattr('stock_recommendation.ak', None)
        result = recommender.get_hot_sectors_cn()
        assert result == []
        assert recommender.last_board_ranking_diagnostics["sectors"]["status"] == "unavailable"

    def test_request_failure_falls_back_to_eastmoney_board(self, recommender, monkeypatch, tmp_path):
        from data.cache import JsonFileCache

        recommender._board_ranking_cache = JsonFileCache("board_rankings_test_eastmoney_sectors", 86400, cache_dir=tmp_path)

        def fake_get(url, **kwargs):
            if "push2.eastmoney.com" in url:
                return _make_mock_response("", json_data={
                    "data": {
                        "diff": [
                            {"f14": "电力行业", "f3": 2.1, "f128": "上海电力"}
                        ]
                    }
                })
            raise Exception("fail")

        monkeypatch.setattr('stock_recommendation.hot_stocks._SINA_SESSION.get', fake_get)

        result = recommender.get_hot_sectors_cn(limit=5)

        assert result[0]["板块"] == "电力行业"
        assert result[0]["数据源"] == "东方财富行业板块"

    def test_request_failure_falls_back_to_sina_industry_board(self, recommender, monkeypatch, tmp_path):
        from data.cache import JsonFileCache

        recommender._board_ranking_cache = JsonFileCache("board_rankings_test_sina_sectors", 86400, cache_dir=tmp_path)

        def fake_get(url, **kwargs):
            if "newSinaHy.php" in url:
                return _make_mock_response(_mock_sina_industry_payload())
            raise Exception("fail")

        monkeypatch.setattr('stock_recommendation.hot_stocks._SINA_SESSION.get', fake_get)
        monkeypatch.setattr('stock_recommendation.ak', None)

        result = recommender.get_hot_sectors_cn(limit=5)

        assert result[0]["板块"] == "电子器件"
        assert result[0]["涨跌幅"] == 1.9
        assert result[0]["领涨股"] == "测试科技"
        assert result[0]["数据源"] == "新浪财经行业板块"

    def test_hot_sector_uses_recent_success_cache_when_sources_unavailable(self, recommender, monkeypatch, tmp_path):
        from data.cache import JsonFileCache

        recommender._board_ranking_cache = JsonFileCache("board_rankings_test_cache_sectors", 86400, cache_dir=tmp_path)
        recommender._board_ranking_cache.set(
            "sectors",
            [{"板块": "PCB", "涨跌幅": 2.2, "领涨股": "测试股", "数据源": "东方财富行业板块"}],
        )
        monkeypatch.setattr(
            'stock_recommendation.hot_stocks._SINA_SESSION.get',
            lambda *args, **kwargs: exec('raise Exception("network down")'),
        )
        monkeypatch.setattr('stock_recommendation.ak', None)

        result = recommender.get_hot_sectors_cn(limit=5)

        assert result[0]["板块"] == "PCB"
        assert "缓存" in result[0]["数据源"]
        assert recommender.last_board_ranking_diagnostics["sectors"]["status"] == "cache"


# ============================================================
# TestGetHotConceptsCN
# ============================================================

class TestGetHotConceptsCN:

    def test_ths_hotlist_concept_board_used_before_wencai(self, recommender, monkeypatch, tmp_path):
        from data.cache import JsonFileCache

        recommender._board_ranking_cache = JsonFileCache("board_rankings_test_ths_hotlist_concepts", 86400, cache_dir=tmp_path)
        monkeypatch.setattr(
            recommender,
            "_get_hot_concepts_ths_hotlist",
            lambda limit=30: [{"板块": "PCB概念", "热度": 24803.5, "涨跌幅": 1.42, "数据源": "同花顺热门概念板块"}],
        )
        monkeypatch.setattr(
            recommender,
            "_get_hot_concepts_wencai",
            lambda limit=30: exec('raise AssertionError("wencai source should not run")'),
        )

        result = recommender.get_hot_concepts_cn(limit=5)

        assert result[0]["板块"] == "PCB概念"
        assert result[0]["热度"] == 24803.5
        assert result[0]["数据源"] == "同花顺热门概念板块"

    def test_returns_list(self, recommender, monkeypatch):
        mock_resp = _make_mock_response(_mock_concept_html())
        monkeypatch.setattr(
            'stock_recommendation.hot_stocks._SINA_SESSION.get',
            lambda url, headers=None, timeout=4: mock_resp,
        )
        result = recommender.get_hot_concepts_cn(limit=10)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_each_concept_has_fields(self, recommender, monkeypatch):
        mock_resp = _make_mock_response(_mock_concept_html())
        monkeypatch.setattr(
            'stock_recommendation.hot_stocks._SINA_SESSION.get',
            lambda url, headers=None, timeout=4: mock_resp,
        )
        result = recommender.get_hot_concepts_cn(limit=5)
        if result:
            s = result[0]
            for key in ['板块', '涨跌幅', '领涨股', '净流入(亿)']:
                assert key in s

    def test_request_failure_marks_unavailable_without_cache(self, recommender, monkeypatch, tmp_path):
        from data.cache import JsonFileCache

        recommender._board_ranking_cache = JsonFileCache("board_rankings_test_empty_concepts_legacy", 1, cache_dir=tmp_path)
        monkeypatch.setattr(
            'stock_recommendation.hot_stocks._SINA_SESSION.get',
            lambda *args, **kwargs: exec('raise Exception("fail")'),
        )
        monkeypatch.setattr('stock_recommendation.ak', None)
        result = recommender.get_hot_concepts_cn()
        assert result == []
        assert recommender.last_board_ranking_diagnostics["concepts"]["status"] == "unavailable"

    def test_request_failure_falls_back_to_eastmoney_concept_board(self, recommender, monkeypatch, tmp_path):
        from data.cache import JsonFileCache

        recommender._board_ranking_cache = JsonFileCache("board_rankings_test_eastmoney_concepts", 86400, cache_dir=tmp_path)

        def fake_get(url, **kwargs):
            if "push2.eastmoney.com" in url:
                return _make_mock_response("", json_data={
                    "data": {
                        "diff": [
                            {"f14": "算力租赁", "f3": 3.2, "f128": "测试股"}
                        ]
                    }
                })
            raise Exception("fail")

        monkeypatch.setattr('stock_recommendation.hot_stocks._SINA_SESSION.get', fake_get)

        result = recommender.get_hot_concepts_cn(limit=5)

        assert result[0]["板块"] == "算力租赁"
        assert result[0]["数据源"] == "东方财富概念板块"

    def test_hot_concept_marks_unavailable_when_sources_and_cache_missing(self, recommender, monkeypatch, tmp_path):
        from data.cache import JsonFileCache

        recommender._board_ranking_cache = JsonFileCache("board_rankings_test_empty", 1, cache_dir=tmp_path)
        monkeypatch.setattr(
            'stock_recommendation.hot_stocks._SINA_SESSION.get',
            lambda *args, **kwargs: exec('raise Exception("network down")'),
        )
        monkeypatch.setattr('stock_recommendation.ak', None)

        result = recommender.get_hot_concepts_cn(limit=5)

        assert result == []
        assert recommender.last_board_ranking_diagnostics["concepts"]["status"] == "unavailable"

    def test_short_term_hot_boards_interleave_concepts_and_sectors(self, recommender, monkeypatch):
        monkeypatch.setattr(
            recommender,
            "get_hot_concepts_cn",
            lambda limit=10: [{"板块": "存储芯片"}, {"板块": "PCB概念"}, {"板块": "共封装光学(CPO)"}],
        )
        monkeypatch.setattr(
            recommender,
            "get_hot_sectors_cn",
            lambda limit=10: [{"板块": "半导体"}, {"板块": "证券"}, {"板块": "银行"}],
        )

        result = recommender._get_short_term_hot_board_rows(limit=4)

        assert [row["name"] for row in result] == ["存储芯片", "半导体", "PCB概念", "证券"]


class TestGetHotIndicesCN:

    def test_get_hot_indices_uses_ths_hotlist(self, recommender, monkeypatch, tmp_path):
        from data.cache import JsonFileCache

        recommender._board_ranking_cache = JsonFileCache("board_rankings_test_ths_hotlist_indices", 86400, cache_dir=tmp_path)
        monkeypatch.setattr(
            recommender,
            "_get_hot_indices_ths_hotlist",
            lambda limit=30: [{"板块": "人工智能", "热度": 1727.5, "涨跌幅": 5.23, "数据源": "同花顺热门指数板块"}],
        )

        result = recommender.get_hot_indices_cn(limit=5)

        assert result[0]["板块"] == "人工智能"
        assert result[0]["热度"] == 1727.5
        assert result[0]["数据源"] == "同花顺热门指数板块"


class TestBoardStatisticsCN:

    def test_normalize_wencai_board_statistics(self, recommender):
        df = pd.DataFrame([
            {
                "指数代码": "881121",
                "指数简称": "半导体",
                "指数@涨跌幅:前复权[20260621]": 2.29,
                "指数@成交额[20260621]": 112000000000,
                "指数@换手率[20260621]": 3.21,
            },
            {
                "指数代码": "885959",
                "指数简称": "PCB概念",
                "指数@涨跌幅:前复权[20260621]": 1.42,
                "指数@成交额[20260621]": 78000000000,
            },
        ])

        result = recommender._normalize_wencai_board_statistics(
            df,
            category="全部",
            sort_by="涨幅",
            source="同花顺板块统计-全部",
        )

        assert [row["板块"] for row in result] == ["半导体", "PCB概念"]
        assert result[0]["代码"] == "881121"
        assert result[0]["类别"] == "全部"
        assert result[0]["涨跌幅"] == 2.29
        assert result[0]["总成交额(亿)"] == 1120

    def test_normalize_wencai_board_statistics_filters_to_ths_level_names(self, recommender):
        df = pd.DataFrame([
            {"指数代码": "884282.TI", "指数简称": "钨", "指数@涨跌幅:前复权[20260621]": 8.17},
            {"指数代码": "881167.TI", "指数简称": "非金属材料", "指数@涨跌幅:前复权[20260621]": 4.99},
            {"指数代码": "881114.TI", "指数简称": "金属新材料", "指数@涨跌幅:前复权[20260621]": 2.45},
        ])

        result = recommender._normalize_wencai_board_statistics(
            df,
            category="行业",
            sort_by="涨幅",
            source="同花顺板块统计-行业",
            allowed_names={"非金属材料", "金属新材料"},
        )

        assert [row["板块"] for row in result] == ["非金属材料", "金属新材料"]

    def test_normalize_wencai_board_statistics_requires_official_names(self, recommender):
        df = pd.DataFrame([
            {"指数代码": "884282.TI", "指数简称": "钨", "指数@涨跌幅:前复权[20260621]": 8.17},
            {"指数代码": "884283.TI", "指数简称": "稀土", "指数@涨跌幅:前复权[20260621]": 6.12},
        ])

        result = recommender._normalize_wencai_board_statistics(
            df,
            category="行业",
            sort_by="涨幅",
            source="同花顺板块统计-行业",
            allowed_names=set(),
        )

        assert result == []

    def test_get_ths_board_statistics_name_set_uses_cache_on_fetch_failure(self, recommender, monkeypatch):
        import stock_recommendation

        recommender._board_ranking_cache.set("board_statistics_ths_names_v1_行业", ["半导体", "非金属材料"])
        monkeypatch.setattr(stock_recommendation, "ak", object())
        monkeypatch.setattr(
            stock_recommendation.hot_stocks,
            "_call_without_proxy_env",
            lambda func: (_ for _ in ()).throw(RuntimeError("offline")),
        )

        result = recommender._get_ths_board_statistics_name_set("行业")

        assert result == {"半导体", "非金属材料"}

    def test_get_ths_board_statistics_name_set_uses_board_code_map_cache(self, recommender, monkeypatch):
        import stock_recommendation

        recommender._board_ranking_cache.set(
            "ths_board_code_map:concept",
            [{"name": "PCB概念", "code": "885959"}, {"name": "存储芯片", "code": "308928"}],
        )
        monkeypatch.setattr(stock_recommendation, "ak", object())
        monkeypatch.setattr(
            stock_recommendation.hot_stocks,
            "_call_without_proxy_env",
            lambda func: (_ for _ in ()).throw(RuntimeError("offline")),
        )

        result = recommender._get_ths_board_statistics_name_set("概念")

        assert result == {"PCB概念", "存储芯片"}

    def test_get_board_statistics_builds_wencai_query(self, recommender, monkeypatch, tmp_path):
        from data.cache import JsonFileCache

        recommender._board_ranking_cache = JsonFileCache("board_rankings_test_statistics", 86400, cache_dir=tmp_path)
        monkeypatch.setattr(recommender, "_get_ths_board_statistics_name_set", lambda category: {"半导体"})

        def fake_wencai(query, source, limit=30, normalizer=None):
            assert query == "板块统计 行业 按涨幅排名"
            assert source == "同花顺板块统计-行业"
            assert callable(normalizer)
            return [{"板块": "半导体", "涨跌幅": 2.29, "类别": "行业", "数据源": source}]

        monkeypatch.setattr(recommender, "_get_hot_boards_wencai", fake_wencai)

        result = recommender.get_board_statistics_cn(category="industry", sort_by="涨幅", limit=5)

        assert result[0]["板块"] == "半导体"
        assert result[0]["类别"] == "行业"

    def test_get_board_statistics_does_not_use_old_unfiltered_cache(self, recommender, monkeypatch, tmp_path):
        from data.cache import JsonFileCache

        recommender._board_ranking_cache = JsonFileCache("board_rankings_test_statistics_version", 86400, cache_dir=tmp_path)
        recommender._board_ranking_cache.set("board_statistics_行业", [{"板块": "钨", "类别": "行业"}])
        monkeypatch.setattr(recommender, "_get_ths_board_statistics_name_set", lambda category: set())

        result = recommender.get_board_statistics_cn(category="行业", sort_by="涨幅", limit=5)

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
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_short_term_hot_board_rows',
            lambda self, limit=6: [{'name': 'PCB', 'leader': ''}],
        )
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_board_constituent_stocks',
            lambda self, board: [
                {'code': '300750', 'name': '宁德时代'},
                {'code': '688981', 'name': '中芯国际'},
                {'code': '002938', 'name': '鹏鼎控股'},
            ],
        )
        result = recommender.get_short_term_recommendations(num_stocks=5)
        assert '000001' not in analyzed
        assert '300750' not in analyzed
        assert '688981' not in analyzed
        assert analyzed == ['002938']
        assert all(not r['symbol'].startswith(('300', '301', '688', '8')) for r in result)
    def test_returns_list(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_short_term',
                            lambda self, code, market='CN': _mock_short_analysis(code))
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_short_term_hot_board_rows',
            lambda self, limit=6: [{'name': 'PCB', 'leader': ''}],
        )
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_board_constituent_stocks',
            lambda self, board: [{'code': '002938', 'name': '鹏鼎控股'}],
        )
        result = recommender.get_short_term_recommendations(num_stocks=5)
        assert isinstance(result, list)

    def test_sorted_descending(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_short_term',
                            lambda self, code, market='CN': _mock_short_analysis(code))
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_short_term_hot_board_rows',
            lambda self, limit=6: [{'name': 'PCB', 'leader': ''}],
        )
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_board_constituent_stocks',
            lambda self, board: [
                {'code': '002938', 'name': '鹏鼎控股'},
                {'code': '300750', 'name': '宁德时代'},
            ],
        )
        result = recommender.get_short_term_recommendations(num_stocks=5)
        if len(result) >= 2:
            assert result[0]['score'] >= result[-1]['score']

    def test_all_candidate_pool_uses_hot_boards_not_financial_head_pool(self, recommender, monkeypatch):
        pool = [
            {'code': '000001', 'name': '平安银行'},
            {'code': '600030', 'name': '中信证券'},
        ]
        monkeypatch.setattr('stock_recommendation.get_popular_cn_stocks', lambda: pool)
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_short_term_hot_board_rows',
            lambda self, limit=6: [{'name': 'PCB', 'leader': ''}],
        )
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_board_constituent_stocks',
            lambda self, board: [
                {'code': '002938', 'name': '鹏鼎控股'},
                {'code': '688981', 'name': '中芯国际'},
            ],
        )
        result = recommender._get_short_term_all_candidate_stocks()
        codes = [item['code'] for item in result]
        assert '000001' not in codes
        assert '600030' not in codes
        assert '002938' in codes
        assert '688981' not in codes
        assert all(item['short_term_sectors'] for item in result)

    def test_board_constituents_use_timeout_guard(self, recommender, monkeypatch):
        calls = []

        def fake_timeout(fetcher, timeout_seconds):
            calls.append(timeout_seconds)
            raise TimeoutError("slow board source")

        monkeypatch.setattr('stock_recommendation.run_with_timeout', fake_timeout)

        result = recommender._get_board_constituent_stocks('PCB')

        assert result == []
        assert calls
        assert calls == [8, 8, 3, 3]

    def test_all_candidate_pool_falls_back_to_hot_board_leader(self, recommender, monkeypatch):
        class DummyFetcher:
            def resolve_stock_input(self, text, market="CN"):
                assert text == '鹏鼎控股'
                return ('002938', '鹏鼎控股')

        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_short_term_hot_board_rows',
            lambda self, limit=6: [{'name': 'PCB', 'leader': '鹏鼎控股'}],
        )
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_board_constituent_stocks',
            lambda self, board: [],
        )
        monkeypatch.setattr('stock_recommendation.StockDataFetcher', lambda: DummyFetcher())

        result = recommender._get_short_term_all_candidate_stocks()

        assert result == [{'code': '002938', 'name': '鹏鼎控股', 'short_term_sectors': ['PCB']}]

    def test_all_requires_stock_own_sector_to_be_hot(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_short_term',
                            lambda self, code, market='CN': _mock_short_analysis(code))
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_short_term_hot_board_rows',
            lambda self, limit=6: [{'name': 'PCB', 'leader': ''}],
        )
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_board_constituent_stocks',
            lambda self, board: [{'code': '002938', 'name': '鹏鼎控股'}] if board == 'PCB' else [],
        )

        result = recommender.get_short_term_recommendations(num_stocks=5)

        assert [item['symbol'] for item in result] == ['002938']
        assert result[0]['sector'] == 'PCB'

    def test_all_requires_pullback_reversal_pattern(self, recommender, monkeypatch):
        failed = _mock_short_analysis('002938')
        failed['strategy_checks']['二板以上涨幅'] = True
        failed['strategy_checks']['回调天数'] = True
        failed['strategy_checks']['回调幅度'] = False
        failed['strategy_checks']['放量反包/涨停板'] = True
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_short_term',
                            lambda self, code, market='CN', include_all_pattern=False: failed.copy())
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_short_term_hot_board_rows',
            lambda self, limit=6: [{'name': 'PCB', 'leader': ''}],
        )
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_board_constituent_stocks',
            lambda self, board: [{'code': '002938', 'name': '鹏鼎控股'}],
        )

        assert recommender.get_short_term_recommendations(num_stocks=5) == []

    def test_short_term_all_pattern_passes_after_surge_pullback_and_volume_reversal(self, recommender):
        dates = pd.date_range("2026-01-01", periods=16, freq="B")
        close = [10, 10.4, 10.8, 11.5, 12.0, 12.6, 13.2, 12.8, 12.3, 12.0, 11.9, 12.4, 12.7, 12.9, 12.5, 13.1]
        data = pd.DataFrame({
            "open": [v - 0.15 for v in close],
            "high": [v + 0.2 for v in close],
            "low": [v - 0.3 for v in close],
            "close": close,
            "volume": [1000, 1100, 1200, 1300, 1400, 1500, 1600, 1200, 1100, 1050, 1000, 1100, 1150, 1200, 1250, 2600],
        }, index=dates)
        data.iloc[-1, data.columns.get_loc("open")] = 12.4
        data.iloc[-1, data.columns.get_loc("high")] = 13.3
        data.iloc[-2, data.columns.get_loc("high")] = 12.8

        checks, details = recommender._evaluate_short_term_all_pattern(data, symbol="002938")

        assert checks["二板以上涨幅"] is True
        assert checks["回调天数"] is True
        assert checks["回调幅度"] is True
        assert checks["放量反包/涨停板"] is True
        assert "涨幅" in details["二板以上涨幅"]
        assert "放量反包" in details["放量反包/涨停板"]

    def test_short_term_volume_requires_5d_ratio(self, recommender):
        dates = pd.date_range("2026-01-01", periods=25, freq="B")
        data = pd.DataFrame({
            "open": [10.0] * 25,
            "high": [10.5] * 25,
            "low": [9.8] * 25,
            "close": [10.2] * 25,
            "volume": [2000] * 15 + [1000] * 9 + [1150],
            "rsi": [50] * 25,
        }, index=dates)
        signals = {"macd": "多头趋势", "kdj": "中性", "boll": "中轨上方，偏多"}

        checks, details = recommender._evaluate_short_term_technical_filters(data, signals)

        assert checks["成交量"] is True
        assert "5日量比 1.15" in details["成交量"]
        assert "20日量比" not in details["成交量"]

    def test_auxiliary_context_does_not_block_when_missing(self, recommender, monkeypatch):
        analysis = _mock_short_analysis('002938')
        analysis['strategy_checks'].update({
            '基本面/估值可用': False,
            '财报/盈利确认': False,
            '资金流确认': False,
            '消息面催化': False,
        })
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_short_term',
                            lambda self, code, market='CN': analysis.copy())
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_short_term_hot_board_rows',
            lambda self, limit=6: [{'name': 'PCB', 'leader': ''}],
        )
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_board_constituent_stocks',
            lambda self, board: [{'code': '002938', 'name': '鹏鼎控股'}],
        )

        result = recommender.get_short_term_recommendations(num_stocks=5)

        assert [item['symbol'] for item in result] == ['002938']


class TestStrategyRecommendations:

    def test_strategy_pool_includes_chinext_and_excludes_star_board(self, recommender, monkeypatch):
        pool = [
            {'code': '300750', 'name': '宁德时代'},
            {'code': '688981', 'name': '中芯国际'},
            {'code': '000001', 'name': '平安银行'},
        ]
        monkeypatch.setattr('stock_recommendation.get_popular_cn_stocks', lambda: pool)
        monkeypatch.setattr('stock_recommendation.CN_STOCK_NAMES_EXTENDED', {})
        monkeypatch.setattr('stock_recommendation.StockDataFetcher._load_stock_name_index', lambda max_age_hours=48: [])

        result = recommender._get_strategy_popular_cn_stocks()

        assert [item['code'] for item in result] == ['300750', '000001']

    def test_aggressive_breakout_requires_three_technical_conditions(self, recommender):
        dates = pd.date_range('2026-01-01', periods=30, freq='B')
        close = np.linspace(10, 13, 30)
        volume = np.full(30, 1000000)
        volume[-1] = 1500000
        data = pd.DataFrame({
            'open': close - 0.1,
            'high': close + 0.2,
            'low': close - 0.2,
            'close': close,
            'volume': volume,
        }, index=dates)

        pattern = recommender._evaluate_breakout_pattern(data)

        assert pattern["matched"] == 3
        assert pattern["conditions"]["均线多头排列"] is True
        assert pattern["conditions"]["突破20日新高"] is True
        assert pattern["conditions"]["明显放量"] is True

    def test_strategy_stock_data_uses_mootdx_then_tencent_before_eastmoney(self, recommender, monkeypatch):
        from data_fetcher import StockDataFetcher

        calls = []
        data = pd.DataFrame({
            'open': np.linspace(10, 12, 20),
            'high': np.linspace(10.2, 12.2, 20),
            'low': np.linspace(9.8, 11.8, 20),
            'close': np.linspace(10, 12, 20),
            'volume': np.full(20, 1000000),
        }, index=pd.date_range('2026-01-01', periods=20, freq='B'))

        def fail_mootdx(self, symbol, period, **kwargs):
            calls.append("mootdx")
            return None

        def ok_tencent(self, symbol, period, **kwargs):
            calls.append("tencent")
            return data

        def fail_eastmoney(self, symbol, period, **kwargs):
            calls.append("eastmoney")
            return None

        monkeypatch.setattr(StockDataFetcher, "_get_cn_stock_data_mootdx", fail_mootdx)
        monkeypatch.setattr(StockDataFetcher, "_get_cn_stock_data_akshare", ok_tencent)
        monkeypatch.setattr(StockDataFetcher, "_get_cn_stock_data_akshare_em", fail_eastmoney)
        monkeypatch.setattr(recommender, "_load_strategy_kline_cache", lambda cache_key: None)
        monkeypatch.setattr(recommender, "_save_strategy_kline_cache", lambda cache_key, data: None)

        result = recommender._get_strategy_stock_data("002001")

        pd.testing.assert_frame_equal(result, data)
        assert result.attrs["data_source"] == "腾讯财经"
        assert calls == ["mootdx", "tencent"]

    def test_realtime_quote_does_not_append_weekend_fake_bar(self, recommender, monkeypatch):
        dates = pd.date_range('2026-05-13', periods=3, freq='B')
        data = pd.DataFrame({
            'open': [10, 10.5, 11],
            'high': [10.2, 10.8, 11.2],
            'low': [9.8, 10.2, 10.8],
            'close': [10, 10.6, 11],
            'volume': [1000000, 1200000, 1500000],
        }, index=dates)

        class DummyFetcher:
            def get_realtime_quote(self, symbol, market):
                return {
                    "price": 11,
                    "open": 11,
                    "high": 11.2,
                    "low": 10.8,
                    "volume": 15000,
                }

        class FakeTimestamp(pd.Timestamp):
            @classmethod
            def now(cls, tz=None):
                return cls("2026-05-16 10:00:00")

        monkeypatch.setattr(pd, "Timestamp", FakeTimestamp)

        result = recommender._merge_realtime_quote(data.copy(), DummyFetcher(), "002001", "CN")

        assert len(result) == len(data)
        assert result.index[-1] == dates[-1]

    def test_strategy_stock_data_drops_weekend_bars(self, recommender):
        data = pd.DataFrame({
            'open': [10, 10.5, 11],
            'high': [10.2, 10.8, 11.2],
            'low': [9.8, 10.2, 10.8],
            'close': [10, 10.6, 11],
            'volume': [1000000, 1200000, 1],
        }, index=pd.to_datetime(["2026-05-15", "2026-05-16", "2026-05-17"]))

        result = recommender._drop_weekend_bars(data)

        assert list(result.index.strftime("%Y-%m-%d")) == ["2026-05-15"]

    def test_multi_factor_extended_info_subprocess_failure_is_contained(self, recommender, monkeypatch):
        import subprocess

        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(args=args, returncode=3221225477, stdout="", stderr="mini_racer.dll crashed")

        monkeypatch.setattr("stock_recommendation.subprocess.run", fake_run)

        result = recommender._get_multi_factor_extended_info("002001")

        assert result["status"] == "source_failed"
        assert "mini_racer" in result["reason"]

    def test_multi_factor_extended_info_uses_cache_before_subprocess(self, recommender, monkeypatch):
        class CachedInfoService:
            def get_cached_stock_extended_info(self, symbol, market="CN", include_deep_layers=True):
                return {
                    "symbol": symbol,
                    "source": "layered_cache",
                    "financial": {},
                    "fund_flow": {},
                    "risk_events": {"announcements": []},
                }

        def fail_run(*args, **kwargs):
            raise AssertionError("subprocess should not run on cache hit")

        monkeypatch.setattr(recommender, "_stock_info_service", CachedInfoService())
        monkeypatch.setattr("stock_recommendation.subprocess.run", fail_run)

        result = recommender._get_multi_factor_extended_info("002001")

        assert result["source"] == "layered_cache"
        assert result["symbol"] == "002001"

    def test_multi_factor_financial_condition_accepts_non_loss(self, recommender):
        ok, note = recommender._evaluate_fundamental_condition({
            "metrics": {"归母净利润": 1000000}
        })

        assert ok is True
        assert "未亏损" in note

    def test_multi_factor_ma_volume_is_independent_from_breakout(self, recommender):
        dates = pd.date_range('2026-01-01', periods=30, freq='B')
        close = np.r_[np.linspace(10, 12, 10), [13.2], np.linspace(11.2, 12.1, 19)]
        volume = np.full(30, 1000000)
        volume[-1] = 1500000
        data = pd.DataFrame({
            'open': close - 0.1,
            'high': close + 0.2,
            'low': close - 0.2,
            'close': close,
            'volume': volume,
        }, index=dates)

        breakout = recommender._evaluate_breakout_pattern(data)
        ok, note, volume_ratio = recommender._evaluate_ma_volume_condition(data)

        assert breakout["conditions"]["突破20日新高"] is False
        assert ok is True
        assert volume_ratio >= 1.2

    def test_multi_factor_uses_7_day_limit_up(self, recommender):
        dates = pd.date_range('2026-01-01', periods=40, freq='B')
        close = np.linspace(10, 12, 40)
        close[-8] = close[-9] * 1.1
        close[-7:] = np.linspace(close[-8] * 0.99, close[-8] * 1.01, 7)
        data = pd.DataFrame({
            'open': close - 0.1,
            'high': close + 0.2,
            'low': close - 0.2,
            'close': close,
            'volume': np.full(40, 1000000),
        }, index=dates)

        assert recommender._has_recent_limit_up(data, days=30) is True
        assert recommender._has_recent_limit_up(data, days=7) is False

    def test_latest_limit_status_detects_limit_up_and_broken_limit(self, recommender):
        dates = pd.date_range('2026-01-01', periods=3, freq='B')
        limit_up = pd.DataFrame({
            'open': [10, 10.2, 10.5],
            'high': [10.2, 10.4, 11.1],
            'low': [9.8, 10.0, 10.4],
            'close': [10, 10, 11.0],
            'volume': [100, 100, 100],
        }, index=dates)
        broken_limit = limit_up.copy()
        broken_limit.loc[dates[-1], 'close'] = 10.6

        assert recommender._latest_limit_status(limit_up)["limit_up"] is True
        assert recommender._latest_limit_status(broken_limit)["broken_limit"] is True

    def test_small_cap_filter_requires_market_cap_below_300_yi(self, recommender, monkeypatch):
        monkeypatch.setattr(
            'stock_recommendation._fetch_tencent_market_cap',
            lambda symbol: (29_900_000_000, "测试股", "腾讯行情"),
        )

        passed, market_cap, note, profile = recommender._passes_small_cap_filter("300750")

        assert passed is True
        assert market_cap == 29_900_000_000
        assert "299.00" in note

    def test_small_cap_filter_rejects_large_market_cap(self, recommender, monkeypatch):
        monkeypatch.setattr(
            'stock_recommendation._fetch_tencent_market_cap',
            lambda symbol: (30_000_000_000, "测试股", "腾讯行情"),
        )

        passed, market_cap, note, profile = recommender._passes_small_cap_filter("300750")

        assert passed is False
        assert market_cap == 30_000_000_000

    def test_aggressive_breakout_rejects_large_market_cap(self, recommender, monkeypatch):
        monkeypatch.setattr(
            'stock_recommendation._fetch_tencent_market_cap',
            lambda symbol: (50_000_000_000, "测试股", "腾讯行情"),
        )

        result = recommender._analyze_aggressive_breakout("300750", stock={"name": "测试股"})

        assert result is None

    def test_strategy_pool_uses_full_stock_name_index(self, recommender, monkeypatch):
        monkeypatch.setattr(
            'stock_recommendation.get_popular_cn_stocks',
            lambda: [{"code": "000001", "name": "平安银行"}],
        )
        monkeypatch.setattr(
            'stock_recommendation.StockDataFetcher._load_stock_name_index',
            lambda max_age_hours=48: [
                {"code": "600088", "name": "中视传媒"},
                {"code": "688981", "name": "中芯国际"},
            ],
        )

        result = recommender._get_strategy_popular_cn_stocks()

        codes = [item["code"] for item in result]
        assert "000001" in codes
        assert "600088" in codes
        assert "688981" not in codes

    def test_aggressive_breakout_checks_market_cap_after_technical_match(self, recommender, monkeypatch):
        stocks = [
            {"code": "300750", "name": "技术未过"},
            {"code": "002415", "name": "技术通过"},
        ]
        monkeypatch.setattr(recommender, "_get_strategy_popular_cn_stocks", lambda limit=None: stocks)
        monkeypatch.setattr(
            recommender,
            "_analyze_aggressive_breakout_technical",
            lambda stock, market='CN', sector_name=None, realtime_quotes=None: {
                "stock": stock,
                "symbol": stock["code"],
                "sector_name": sector_name,
                "pattern": {
                    "latest": pd.Series({
                        "close": 10,
                        "ma5": 10,
                        "ma10": 9,
                        "ma20": 8,
                        "macd": 0,
                        "macd_signal": 0,
                        "macd_hist": 0,
                        "rsi": 50,
                        "rsi_6": 50,
                        "rsi_12": 50,
                        "rsi_24": 50,
                        "kdj_k": 50,
                        "kdj_d": 45,
                        "kdj_j": 60,
                        "boll_upper": 11,
                        "boll_mid": 10,
                        "boll_lower": 9,
                        "boll_width": 0.1,
                        "boll_percent": 50,
                    }),
                    "conditions": {"均线多头排列": True, "突破20日新高": True, "明显放量": True},
                    "matched": 3,
                    "volume_ratio": 1.5,
                    "change_pct": 2.0,
                    "recent_high_20": 10,
                },
            } if stock["code"] == "002415" else None,
        )
        checked = []
        monkeypatch.setattr(
            recommender,
            "_passes_small_cap_filter",
            lambda symbol, market='CN': checked.append(symbol) or (True, 20_000_000_000, "总市值 200.00 亿", {"market_cap": 20_000_000_000}),
        )

        result = recommender.get_aggressive_breakout_recommendations(num_stocks=5)

        assert [item["symbol"] for item in result] == ["002415"]
        assert checked == ["002415"]

    def test_aggressive_breakout_uses_full_strategy_pool_without_limit(self, recommender, monkeypatch):
        calls = []
        stocks = [{"code": f"002{i:03d}", "name": f"候选{i}"} for i in range(3)]
        monkeypatch.setattr(
            recommender,
            "_get_strategy_popular_cn_stocks",
            lambda limit=None: calls.append(limit) or stocks,
        )
        monkeypatch.setattr(recommender, "_run_aggressive_breakout_pool", lambda stocks, num_stocks, diagnostics=None, progress_callback=None: [])

        result = recommender.get_aggressive_breakout_recommendations(num_stocks=5)

        assert result == []
        assert calls == [None]

    def test_aggressive_breakout_records_diagnostics(self, recommender, monkeypatch):
        stocks = [{"code": "002415", "name": "候选A"}, {"code": "002001", "name": "候选B"}]
        monkeypatch.setattr(recommender, "_get_strategy_popular_cn_stocks", lambda limit=None: stocks)
        monkeypatch.setattr(
            recommender,
            "_analyze_aggressive_breakout_technical",
            lambda stock, market='CN', sector_name=None, realtime_quotes=None: {
                "stock": stock,
                "symbol": stock["code"],
                "sector_name": sector_name,
                "pattern": {
                    "latest": pd.Series({
                        "close": 10,
                        "ma5": 10,
                        "ma10": 9,
                        "ma20": 8,
                        "macd": 0,
                        "macd_signal": 0,
                        "macd_hist": 0,
                        "rsi": 50,
                        "rsi_6": 50,
                        "rsi_12": 50,
                        "rsi_24": 50,
                        "kdj_k": 50,
                        "kdj_d": 45,
                        "kdj_j": 60,
                        "boll_upper": 11,
                        "boll_mid": 10,
                        "boll_lower": 9,
                        "boll_width": 0.1,
                        "boll_percent": 50,
                    }),
                    "conditions": {"均线多头排列": True, "突破20日新高": True, "明显放量": True},
                    "matched": 3,
                    "volume_ratio": 1.5,
                    "change_pct": 2.0,
                    "recent_high_20": 10,
                },
            } if stock["code"] == "002415" else None,
        )
        monkeypatch.setattr(
            recommender,
            "_passes_small_cap_filter",
            lambda symbol, market='CN': (True, 20_000_000_000, "总市值 200.00 亿", {"market_cap": 20_000_000_000}),
        )

        result = recommender.get_aggressive_breakout_recommendations(num_stocks=5)

        assert [item["symbol"] for item in result] == ["002415"]
        assert recommender.last_aggressive_diagnostics["raw_pool"] == 2
        assert recommender.last_aggressive_diagnostics["technical_passed"] == 1
        assert recommender.last_aggressive_diagnostics["result_count"] == 1

    def test_multi_factor_shortlist_avoids_deep_fetch_for_non_shortlisted(self, recommender, monkeypatch):
        stocks = [
            {"code": "002001", "name": "候选A"},
            {"code": "002002", "name": "候选B"},
            {"code": "300001", "name": "候选C"},
        ]
        monkeypatch.setattr(recommender, "_get_strategy_popular_cn_stocks", lambda limit=None: stocks)
        monkeypatch.setattr(recommender, "_prefilter_small_cap_stocks", lambda stocks, market='CN': stocks)
        monkeypatch.setattr(
            recommender,
            "_analyze_multi_factor_light",
            lambda stock, market='CN', sector_name=None, realtime_quotes=None: {
                "stock": stock,
                "light_score": {"002001": 90, "002002": 70, "300001": 0}[stock["code"]],
            } if stock["code"] != "300001" else None,
        )
        analyzed = []
        monkeypatch.setattr(
            recommender,
            "_analyze_multi_factor",
            lambda symbol, stock=None, sector_name=None, diagnostics=None: analyzed.append(symbol) or None,
        )

        result = recommender.get_multi_factor_recommendations(num_stocks=1)

        assert result == []
        assert analyzed == ["002001", "002002"]

    def test_multi_factor_uses_full_strategy_pool_without_limit(self, recommender, monkeypatch):
        calls = []
        stocks = [{"code": f"002{i:03d}", "name": f"候选{i}"} for i in range(3)]
        monkeypatch.setattr(
            recommender,
            "_get_strategy_popular_cn_stocks",
            lambda limit=None: calls.append(limit) or stocks,
        )
        monkeypatch.setattr(recommender, "_shortlist_multi_factor_candidates", lambda stocks, num_stocks, diagnostics=None, progress_callback=None: [])

        result = recommender.get_multi_factor_recommendations(num_stocks=5)

        assert result == []
        assert calls == [None]

    def test_multi_factor_emits_stage_progress(self, recommender, monkeypatch):
        stocks = [{"code": "002001", "name": "候选A"}]
        events = []
        monkeypatch.setattr(recommender, "_get_strategy_popular_cn_stocks", lambda limit=None: stocks)
        monkeypatch.setattr(recommender, "_prefilter_small_cap_stocks", lambda stocks, market='CN': stocks)
        monkeypatch.setattr(
            recommender,
            "_analyze_multi_factor_light",
            lambda stock, market='CN', sector_name=None, realtime_quotes=None: {
                "passed": True,
                "stock": stock,
                "light_score": 80,
            },
        )
        monkeypatch.setattr(recommender, "_analyze_multi_factor", lambda symbol, stock=None, sector_name=None, diagnostics=None: None)

        result = recommender.get_multi_factor_recommendations(
            num_stocks=1,
            progress_callback=lambda stage, percent, metrics: events.append((stage, percent, metrics)),
        )

        assert result == []
        stages = [event[0] for event in events]
        assert "股票池" in stages
        assert "市值过滤" in stages
        assert "K线轻筛" in stages
        assert "深度检查" in stages
        assert "完成" in stages

    def test_multi_factor_light_prefilter_rejects_kline_impossible_cases(self, recommender, monkeypatch):
        dates = pd.date_range('2026-01-01', periods=40, freq='B')
        close = np.linspace(10, 20, 40)
        data = pd.DataFrame({
            'open': close,
            'high': close * 1.01,
            'low': close * 0.99,
            'close': close,
            'volume': np.full(40, 1000000),
        }, index=dates)
        monkeypatch.setattr(recommender, "_get_strategy_stock_data", lambda *args, **kwargs: data)
        monkeypatch.setattr(recommender, "_merge_realtime_quote", lambda data, *args, **kwargs: data)
        monkeypatch.setattr(recommender, "_evaluate_ma_volume_condition", lambda data: (False, "技术不满足", 0.8))
        monkeypatch.setattr(recommender, "_has_recent_limit_up_touch", lambda data, days=15: (False, "无涨停"))
        monkeypatch.setattr(recommender, "_has_three_day_rise", lambda data: (False, "未连涨"))

        result = recommender._analyze_multi_factor_light({"code": "002001", "name": "测试股"})

        assert result["passed"] is False
        assert result["reason"] in {"非短期过热", "K线核心因子不足"}

    def test_aggressive_breakout_emits_stage_progress(self, recommender, monkeypatch):
        stocks = [{"code": "002415", "name": "候选A"}]
        events = []
        monkeypatch.setattr(recommender, "_get_strategy_popular_cn_stocks", lambda limit=None: stocks)
        monkeypatch.setattr(recommender, "_analyze_aggressive_breakout_technical", lambda stock, market='CN', sector_name=None, realtime_quotes=None: None)

        result = recommender.get_aggressive_breakout_recommendations(
            num_stocks=1,
            progress_callback=lambda stage, percent, metrics: events.append((stage, percent, metrics)),
        )

        assert result == []
        stages = [event[0] for event in events]
        assert "股票池" in stages
        assert "当日实时价量" in stages
        assert "K线轻筛" in stages
        assert "市值过滤" in stages
        assert "完成" in stages

    def test_multi_factor_allows_missing_bonus_catalyst_and_limit_up(self, recommender, monkeypatch):
        dates = pd.date_range('2026-01-01', periods=40, freq='B')
        close = np.linspace(10, 12, 40)
        close[-20:] = np.linspace(10, 13, 20)
        volume = np.full(40, 1000000)
        volume[-1] = 1500000
        data = pd.DataFrame({
            'open': close - 0.1,
            'high': close + 0.2,
            'low': close - 0.2,
            'close': close,
            'volume': volume,
        }, index=dates)
        stock = {
            "code": "002001",
            "name": "测试股",
            "_market_cap": 20_000_000_000,
            "_cap_note": "总市值 200.00 亿",
            "_profile": {"market_cap": 20_000_000_000},
            "_prefetched_data": data,
        }
        monkeypatch.setattr(
            recommender,
            "_get_multi_factor_extended_info",
            lambda symbol, market='CN': {
                "fund_flow": {"main_net_inflow": 30_000_000},
                "financial": {"metrics": {"归母净利润": 1000000}},
                "news": [],
                "market_news": [],
                "research": {"reports": []},
                "risk_events": {"announcements": []},
            },
        )

        result = recommender._analyze_multi_factor("002001", stock=stock)

        assert result is not None
        assert result["required_checks"]["市值<300亿"] is True
        assert "个股资金流入" not in result["core_checks"]
        assert "消息/公告/研报催化" not in result["strategy_checks"]
        assert "消息催化" not in result["strategy_details"]
        assert result["rating"] == "多因子共振"

    def test_multi_factor_score_mode_accepts_three_of_five_core_factors(self, recommender, monkeypatch):
        dates = pd.date_range('2026-01-01', periods=40, freq='B')
        close = np.linspace(10, 13, 40)
        volume = np.full(40, 1000000)
        volume[-1] = 1500000
        data = pd.DataFrame({
            'open': close - 0.1,
            'high': close + 0.2,
            'low': close - 0.2,
            'close': close,
            'volume': volume,
        }, index=dates)
        stock = {
            "code": "002001",
            "name": "测试股",
            "_market_cap": 20_000_000_000,
            "_cap_note": "总市值 200.00 亿",
            "_profile": {"market_cap": 20_000_000_000},
            "_prefetched_data": data,
        }
        monkeypatch.setattr(
            recommender,
            "_get_multi_factor_extended_info",
            lambda symbol, market='CN': {
                "fund_flow": {"main_net_inflow": 30_000_000},
                "financial": {"metrics": {"归母净利润": 1000000}},
                "news": [],
                "market_news": [],
                "research": {"reports": []},
                "risk_events": {"announcements": []},
            },
        )

        result = recommender._analyze_multi_factor("002001", stock=stock)

        assert result is not None
        assert result["core_matched"] >= 3
        assert result["score"] >= 70
        assert result["core_checks"]["主力净流入趋势≥3000万"] is True
        assert "消息/公告/研报催化" not in result["core_checks"]

    def test_multi_factor_score_mode_rejects_below_three_core_factors(self, recommender, monkeypatch):
        dates = pd.date_range('2026-01-01', periods=40, freq='B')
        close = np.linspace(10, 13, 40)
        volume = np.full(40, 1000000)
        volume[-1] = 1500000
        data = pd.DataFrame({
            'open': close - 0.1,
            'high': close + 0.2,
            'low': close - 0.2,
            'close': close,
            'volume': volume,
        }, index=dates)
        stock = {
            "code": "002001",
            "name": "测试股",
            "_market_cap": 20_000_000_000,
            "_cap_note": "总市值 200.00 亿",
            "_profile": {"market_cap": 20_000_000_000},
            "_prefetched_data": data,
        }
        diagnostics = {}
        monkeypatch.setattr(
            recommender,
            "_get_multi_factor_extended_info",
            lambda symbol, market='CN': {
                "fund_flow": {},
                "financial": {"metrics": {"归母净利润": -1000000}},
                "news": [],
                "market_news": [],
                "research": {"reports": []},
                "risk_events": {"announcements": []},
            },
        )

        result = recommender._analyze_multi_factor("002001", stock=stock, diagnostics=diagnostics)

        assert result is None
        assert any(reason.startswith("评分不足") for reason in diagnostics["deep_failures"])
        assert diagnostics["core_factor_summary"]["主力净流入趋势≥3000万"]["failed"] == 1
        assert diagnostics["deep_data_quality"]["资金流数据"]["missing"] == 1

    def test_multi_factor_requires_new_fund_and_activity_conditions(self, recommender, monkeypatch):
        dates = pd.date_range('2026-01-01', periods=40, freq='B')
        close = np.linspace(10, 12, 40)
        close[-15] = close[-16] * 1.1
        close[-14:-4] = np.linspace(close[-15] * 0.98, 11.2, 10)
        close[-4:] = [11.2, 11.4, 11.7, 12.0]
        high = close + 0.2
        high[-15] = close[-16] * 1.1
        volume = np.full(40, 1000000)
        volume[-1] = 1500000
        data = pd.DataFrame({
            'open': close - 0.1,
            'high': high,
            'low': close - 0.2,
            'close': close,
            'volume': volume,
        }, index=dates)
        stock = {
            "code": "002001",
            "name": "测试股",
            "_market_cap": 20_000_000_000,
            "_cap_note": "总市值 200.00 亿",
            "_profile": {"market_cap": 20_000_000_000},
            "_prefetched_data": data,
        }
        monkeypatch.setattr(
            recommender,
            "_get_multi_factor_extended_info",
            lambda symbol, market='CN': {
                "fund_flow": {"main_net_inflow": 30_000_000},
                "financial": {"metrics": {"归母净利润": 1000000}},
                "news": [{"title": "利好新闻", "date": pd.Timestamp.now().strftime("%Y-%m-%d")}],
                "market_news": [],
                "research": {"reports": []},
                "risk_events": {"announcements": []},
            },
        )

        result = recommender._analyze_multi_factor("002001", stock=stock)

        assert result is not None
        assert result["core_checks"]["连涨3日"] is True
        assert result["core_checks"]["主力净流入趋势≥3000万"] is True
        assert result["core_checks"]["15日内涨停"] is True
        assert "消息/公告/研报催化" not in result["strategy_checks"]
        assert "个股资金流入" not in result["strategy_checks"]

    def test_multi_factor_limit_up_factor_accepts_intraday_touch(self, recommender, monkeypatch):
        dates = pd.date_range('2026-01-01', periods=40, freq='B')
        close = np.linspace(10, 12, 40)
        close[-15] = close[-16] * 1.03
        high = close + 0.2
        high[-15] = close[-16] * 1.1
        close[-4:] = [11.2, 11.4, 11.7, 12.0]
        volume = np.full(40, 1000000)
        volume[-1] = 1500000
        data = pd.DataFrame({
            'open': close - 0.1,
            'high': high,
            'low': close - 0.2,
            'close': close,
            'volume': volume,
        }, index=dates)
        stock = {
            "code": "002001",
            "name": "测试股",
            "_market_cap": 20_000_000_000,
            "_cap_note": "总市值 200.00 亿",
            "_profile": {"market_cap": 20_000_000_000},
            "_prefetched_data": data,
        }
        monkeypatch.setattr(
            recommender,
            "_get_multi_factor_extended_info",
            lambda symbol, market='CN': {
                "fund_flow": {"main_net_inflow": 30_000_000},
                "financial": {"metrics": {"归母净利润": 1000000}},
                "risk_events": {"announcements": []},
            },
        )

        result = recommender._analyze_multi_factor("002001", stock=stock)

        assert result is not None
        assert result["core_checks"]["15日内涨停"] is True
        assert "近15日出现涨停" in result["strategy_details"]["15日涨停"]

    def test_multi_factor_rejects_latest_limit_up_or_broken_limit(self, recommender, monkeypatch):
        dates = pd.date_range('2026-01-01', periods=40, freq='B')
        close = np.linspace(10, 12, 40)
        close[-20:] = np.linspace(10, 13, 20)
        close[-2] = 10
        close[-1] = 10.6
        high = close + 0.2
        high[-1] = 11.0
        volume = np.full(40, 1000000)
        volume[-1] = 1500000
        data = pd.DataFrame({
            'open': close - 0.1,
            'high': high,
            'low': close - 0.2,
            'close': close,
            'volume': volume,
        }, index=dates)
        stock = {
            "code": "002001",
            "name": "测试股",
            "_market_cap": 20_000_000_000,
            "_cap_note": "总市值 200.00 亿",
            "_profile": {"market_cap": 20_000_000_000},
            "_prefetched_data": data,
        }
        monkeypatch.setattr(
            recommender,
            "_get_multi_factor_extended_info",
            lambda symbol, market='CN': {
                "fund_flow": {"main_net_inflow": 1000000},
                "financial": {"metrics": {"归母净利润": 1000000}},
                "news": [],
                "market_news": [],
                "research": {"reports": []},
                "risk_events": {"announcements": []},
            },
        )

        result = recommender._analyze_multi_factor("002001", stock=stock)

        assert result is None

    def test_multi_factor_records_diagnostics_when_no_results(self, recommender, monkeypatch):
        stocks = [{"code": "002001", "name": "候选A"}]
        monkeypatch.setattr(recommender, "_get_strategy_popular_cn_stocks", lambda limit=None: stocks)
        monkeypatch.setattr(recommender, "_prefilter_small_cap_stocks", lambda stocks, market='CN': stocks)
        monkeypatch.setattr(
            recommender,
            "_analyze_multi_factor_light",
            lambda stock, market='CN', sector_name=None, realtime_quotes=None: {"passed": False, "reason": "K线接口失败"},
        )

        result = recommender.get_multi_factor_recommendations(num_stocks=5)

        assert result == []
        assert recommender.last_multi_factor_diagnostics["raw_pool"] == 1
        assert recommender.last_multi_factor_diagnostics["light_failures"]["K线接口失败"] == 1
        assert recommender.last_multi_factor_diagnostics["result_count"] == 0

    def test_multi_factor_ignores_research_catalyst_as_core_condition(self, recommender, monkeypatch):
        dates = pd.date_range(pd.Timestamp.now().normalize() - pd.Timedelta(days=60), periods=40, freq='B')
        close = np.linspace(10, 12, 40)
        close[-7] = close[-8] * 1.1
        close[-6:] = np.linspace(close[-7] * 0.99, close[-7] * 1.01, 6)
        volume = np.full(40, 1000000)
        volume[-1] = 1500000
        data = pd.DataFrame({
            'open': close - 0.1,
            'high': close + 0.2,
            'low': close - 0.2,
            'close': close,
            'volume': volume,
        }, index=dates)
        stock = {
            "code": "002001",
            "name": "测试股",
            "_market_cap": 20_000_000_000,
            "_cap_note": "总市值 200.00 亿",
            "_profile": {"market_cap": 20_000_000_000},
            "_prefetched_data": data,
        }
        monkeypatch.setattr(
            recommender,
            "_get_multi_factor_extended_info",
            lambda symbol, market='CN': {
                "fund_flow": {"main_net_inflow": 1000000},
                "financial": {"metrics": {"归母净利润": 1000000}},
                "news": [],
                "market_news": [],
                "research": {"reports": [{
                    "title": "测试研报",
                    "date": (pd.Timestamp.now().normalize() - pd.Timedelta(days=20)).strftime("%Y-%m-%d"),
                }]},
                "risk_events": {"announcements": []},
            },
        )

        result = recommender._analyze_multi_factor("002001", stock=stock)

        assert result is not None
        assert "消息/公告/研报催化" not in result["strategy_checks"]
        assert "消息催化" not in result["strategy_details"]
        assert "催化依据" not in result["strategy_details"]

    def test_multi_factor_catalyst_basis_classifies_positive_and_risk(self, recommender, monkeypatch):
        dates = pd.date_range(pd.Timestamp.now().normalize() - pd.Timedelta(days=60), periods=40, freq='B')
        close = np.linspace(10, 12, 40)
        close[-7] = close[-8] * 1.1
        close[-6:] = np.linspace(close[-7] * 0.99, close[-7] * 1.01, 6)
        volume = np.full(40, 1000000)
        volume[-1] = 1500000
        data = pd.DataFrame({
            'open': close - 0.1,
            'high': close + 0.2,
            'low': close - 0.2,
            'close': close,
            'volume': volume,
        }, index=dates)
        stock = {
            "code": "002001",
            "name": "测试股",
            "_market_cap": 20_000_000_000,
            "_cap_note": "总市值 200.00 亿",
            "_profile": {"market_cap": 20_000_000_000},
            "_prefetched_data": data,
        }
        today = pd.Timestamp.now().strftime("%Y-%m-%d")
        monkeypatch.setattr(
            recommender,
            "_get_multi_factor_extended_info",
            lambda symbol, market='CN': {
                "fund_flow": {"main_net_inflow": 1000000},
                "financial": {"metrics": {"归母净利润": 1000000}},
                "news": [{"title": "公司签订重大合同订单", "date": today, "source": "东方财富个股新闻"}],
                "market_news": [],
                "research": {"reports": [{
                    "title": "机构覆盖首次给予买入评级",
                    "date": today,
                    "org": "测试证券",
                }]},
                "risk_events": {"announcements": [{"title": "关于诉讼进展公告", "date": today, "source": "东方财富个股公告"}]},
            },
        )

        result = recommender._analyze_multi_factor("002001", stock=stock)

        assert result is None

    def test_strategy_kline_uses_local_cache_before_api(self, recommender, monkeypatch):
        dates = pd.date_range("2026-01-01", periods=30, freq="B")
        data = pd.DataFrame({
            "open": np.linspace(10, 12, 30),
            "high": np.linspace(10.2, 12.2, 30),
            "low": np.linspace(9.8, 11.8, 30),
            "close": np.linspace(10, 12, 30),
            "volume": np.full(30, 1000000),
        }, index=dates)
        monkeypatch.setattr(recommender, "_load_strategy_kline_cache", lambda cache_key: data.copy())
        called = {"api": False}
        class DummyFetcher:
            def _get_cn_stock_data_sina_fallback(self, symbol, period):
                called["api"] = True
                return None
            def _get_cn_stock_data_akshare(self, symbol, period):
                called["api"] = True
                return None
            def _get_cn_stock_data_akshare_em(self, symbol, period):
                called["api"] = True
                return None
            def _load_offline_cache(self, symbol):
                called["api"] = True
                return None

        result = recommender._get_strategy_stock_data("002001", fetcher=DummyFetcher())

        assert result is not None
        assert len(result) == 30
        assert result.attrs["data_source"] == "策略K线本地缓存"
        assert called["api"] is False

# ============================================================
# TestGetSectorShortTerm
# ============================================================
class TestGetSectorShortTerm:

    def test_invalid_sector_returns_empty(self, recommender):
        result = recommender.get_sector_short_term_recommendations('不存在的板块')
        assert result == []

    def test_valid_sector_returns_list(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_short_term',
                            lambda self, code, market='CN': _mock_short_analysis(code))
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_short_term_hot_board_list',
            lambda self: ['苹果概念'],
        )
        result = recommender.get_sector_short_term_recommendations('苹果概念', num_stocks=3)
        assert isinstance(result, list)

    def test_removed_short_term_sectors_return_empty(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_short_term',
                            lambda self, code, market='CN': _mock_short_analysis(code))
        assert recommender.get_sector_short_term_recommendations('电力', num_stocks=5) == []
        assert recommender.get_sector_short_term_recommendations('算力租赁', num_stocks=5) == []

    def test_hot_board_is_auxiliary_for_allowed_sector(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_short_term',
                            lambda self, code, market='CN': _mock_short_analysis(code))
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_short_term_hot_board_list',
            lambda self: ['PCB'],
        )
        result = recommender.get_sector_short_term_recommendations('苹果概念', num_stocks=3)
        assert result
        assert all(item["strategy_checks"]["热门板块"] is False for item in result)

    def test_us_catalyst_is_auxiliary_for_apple_tesla_sector(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_short_term',
                            lambda self, code, market='CN': _mock_short_analysis(code))
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_short_term_hot_board_list',
            lambda self: [],
        )
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_short_term_us_catalyst',
            lambda self, sector: {
                'available': True,
                'symbol': 'AAPL',
                'name': '苹果',
                'delta': 4,
                'detail': '苹果(AAPL) 近一交易日上涨 2.50%，美股联动偏利好',
            },
        )

        result = recommender.get_sector_short_term_recommendations('苹果概念', num_stocks=3)

        assert result
        assert result[0]['score'] == min(100, _mock_short_analysis(result[0]['symbol'])['score'] + 4)
        assert result[0]['strategy_checks']['美股消息催化'] is True
        assert 'AAPL' in result[0]['strategy_details']['美股消息催化']

    def test_missing_us_catalyst_does_not_block_sector_result(self, recommender, monkeypatch):
        monkeypatch.setattr('stock_recommendation.StockRecommender._analyze_short_term',
                            lambda self, code, market='CN': _mock_short_analysis(code))
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_short_term_hot_board_list',
            lambda self: [],
        )
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_short_term_us_catalyst',
            lambda self, sector: {
                'available': False,
                'symbol': 'TSLA',
                'name': '特斯拉',
                'delta': 0,
                'detail': '特斯拉(TSLA) 美股行情获取失败',
            },
        )

        result = recommender.get_sector_short_term_recommendations('特斯拉概念', num_stocks=3)

        assert result
        assert result[0]['strategy_checks']['美股消息催化'] is False
        assert '获取失败' in result[0]['strategy_details']['美股消息催化']

    def test_filters_unrecommendable_board_sector_stocks(self, recommender, monkeypatch):
        sector_pool = {
            '苹果概念': [
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
        monkeypatch.setattr(
            'stock_recommendation.StockRecommender._get_short_term_hot_board_list',
            lambda self: ['苹果概念'],
        )
        result = recommender.get_sector_short_term_recommendations('苹果概念', num_stocks=5)
        assert analyzed == ['300750', '000001', '600519']
        assert all(not r['symbol'].startswith(('688', '8')) for r in result)


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
    def __init__(self, html, status_code=200, encoding='utf-8', json_data=None):
        self.text = html
        self.status_code = status_code
        self.encoding = encoding
        self._json_data = json_data

    def json(self):
        return self._json_data or {}


def _make_mock_response(html, status_code=200, json_data=None):
    """创建一个模拟的 requests.Response"""
    return MockResponse(html, status_code, json_data=json_data)


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


def _mock_sina_industry_payload():
    return (
        'var S_Finance_bankuai_sinaindustry = {'
        '"new_dzqj":"new_dzqj,电子器件,152,33.27,0.62,1.90,15234516016,342978292636,sz300319,20.017,27.760,4.630,测试科技",'
        '"new_blhy":"new_blhy,玻璃行业,19,22.00,-0.43,-1.94,1629824817,35915185654,sh600184,5.812,28.220,1.550,光电股份"'
        '};'
    )


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
        'strategy_checks': {
            '成交量': True,
            'MACD': True,
            'RSI': True,
            'KDJ': False,
            'BOLL': False,
            '技术命中数': 3,
            '二板以上涨幅': True,
            '回调天数': True,
            '回调幅度': True,
            '放量反包/涨停板': True,
        },
        'strategy_details': {},
        'indicators': {},
    }


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
