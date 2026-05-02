"""飞书机器人 API 服务测试"""
import pytest
import json
import pandas as pd
import numpy as np


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_data_fetcher(monkeypatch):
    """Mock 数据获取 — 返回30天数据"""
    dates = pd.date_range('2025-06-01', periods=30, freq='B')
    n = 30
    close = 10 + np.cumsum(np.random.RandomState(0).randn(n) * 0.2)
    df = pd.DataFrame({
        'open': close - 0.1, 'high': close + 0.3, 'low': close - 0.3, 'close': close,
        'volume': np.random.RandomState(1).randint(1000000, 5000000, n),
    }, index=dates)
    from data_fetcher import StockDataFetcher
    monkeypatch.setattr(StockDataFetcher, 'get_stock_data',
                       lambda self, symbol, period='3mo', market='CN': df)
    return df


# ============================================================
# TestHandleCommand
# ============================================================

class TestHandleCommand:

    def test_watchlist_command(self, mock_data_fetcher, monkeypatch, tmp_path):
        """ /watchlist → 返回自选股摘要"""
        # Mock _get_watchlist_text 直接返回含自选股的文本
        monkeypatch.setattr('api_server._get_watchlist_text', lambda: '平安银行 · A股 | ¥12.00')
        from api_server import handle_command
        result = handle_command('/watchlist')
        assert '平安银行' in result

    def test_hot_command_cn(self, monkeypatch):
        """ /hot → 返回热门推荐"""
        monkeypatch.setattr('api_server._get_hot_text', lambda market='CN': f'热门 [{market}]')
        from api_server import handle_command
        result = handle_command('/hot')
        assert 'CN' in result

    def test_hot_command_with_market(self, monkeypatch):
        """ /hot HK → 港股热门"""
        monkeypatch.setattr('api_server._get_hot_text', lambda market='CN': f'热门 [{market}]')
        from api_server import handle_command
        result = handle_command('/hot HK')
        assert 'HK' in result

    def test_analysis_command(self, monkeypatch):
        """ /analysis <symbol> → 个股分析"""
        monkeypatch.setattr('api_server._get_analysis_text',
                           lambda symbol, market='CN': f'{symbol} [{market}] 分析')
        from api_server import handle_command
        result = handle_command('/analysis 000001')
        assert '000001' in result

    def test_analysis_with_market(self, monkeypatch):
        """ /analysis AAPL US → 美股分析"""
        monkeypatch.setattr('api_server._get_analysis_text',
                           lambda symbol, market='CN': f'{symbol} [{market}] 分析')
        from api_server import handle_command
        result = handle_command('/analysis AAPL US')
        assert 'AAPL' in result and 'US' in result

    def test_symbol_as_command(self, mock_data_fetcher, monkeypatch):
        """ 直接输入代码 → 快速分析"""
        monkeypatch.setattr('api_server._get_analysis_text',
                           lambda symbol, market='CN': f'快速分析 {symbol}')
        from api_server import handle_command
        result = handle_command('000001')
        assert '000001' in result

    def test_unknown_command(self):
        """ 非命令非代码输入 → 帮助信息"""
        from api_server import handle_command
        result = handle_command('帮帮我')
        assert '支持以下命令' in result or '/watchlist' in result

    def test_analysis_missing_symbol(self):
        """ /analysis 无参数 → 提示"""
        from api_server import handle_command
        result = handle_command('/analysis')
        assert '代码' in result or '例如' in result


# ============================================================
# TestApiEndpoints
# ============================================================

class TestApiEndpoints:

    def test_root_endpoint(self):
        """ GET / → 返回服务信息"""
        from api_server import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.get('/')
        assert response.status_code == 200
        data = response.json()
        assert 'service' in data

    def test_health_endpoint(self):
        """ GET /health → 返回 ok"""
        from api_server import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.get('/health')
        assert response.status_code == 200
        assert response.json()['status'] == 'ok'

    def test_feishu_challenge(self):
        """ 飞书 URL 验证 challenge"""
        from api_server import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.post('/webhook/feishu', json={'challenge': 'test123', 'token': ''})
        assert response.status_code == 200
        assert response.json()['challenge'] == 'test123'

    def test_feishu_text_message(self, mock_data_fetcher, monkeypatch):
        """ 飞书文本消息 → 返回命令结果"""
        monkeypatch.setattr('api_server._get_watchlist_text', lambda: '自选股摘要')
        monkeypatch.setattr('api_server._get_analysis_text',
                           lambda symbol, market='CN': f'分析 {symbol}')
        monkeypatch.setattr('api_server._get_hot_text', lambda market='CN': '热门推荐')

        from api_server import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.post('/webhook/feishu', json={
            'event': {
                'message': {
                    'message_type': 'text',
                    'content': json.dumps({'text': '/watchlist'})
                }
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert data['data']['reply'] == '自选股摘要'

    def test_api_watchlist_empty(self):
        """ API /api/watchlist 返回 watchlist 数据（当前 json 为空）"""
        from api_server import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.get('/api/watchlist')
        assert response.status_code == 200
        data = response.json()
        # 当前 watchlist.json 为空，message 会说明
        assert 'watchlist' in data or 'message' in data

    def test_api_analysis(self, mock_data_fetcher):
        """ API /api/analysis?symbol=000001 返回分析结果"""
        from api_server import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.get('/api/analysis?symbol=000001&market=CN')
        assert response.status_code == 200
        data = response.json()
        assert 'symbol' in data
