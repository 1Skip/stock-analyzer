"""AI 智能解读模块测试"""
import json
import pytest
import pandas as pd
import numpy as np


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def sample_data():
    """构造含完整指标列的数据"""
    dates = pd.date_range('2026-03-01', periods=60, freq='B')
    np.random.seed(42)
    close = np.cumsum(np.random.randn(60) * 0.5) + 10.0
    df = pd.DataFrame({
        'open': close - 0.1,
        'high': close + 0.3,
        'low': close - 0.3,
        'close': close,
        'volume': np.random.randint(1000000, 5000000, 60),
        'macd': np.random.randn(60) * 0.5,
        'macd_signal': np.random.randn(60) * 0.3,
        'macd_hist': np.random.randn(60) * 0.2,
        'rsi_6': np.random.uniform(30, 70, 60),
        'rsi_12': np.random.uniform(30, 70, 60),
        'rsi_24': np.random.uniform(30, 70, 60),
        'kdj_k': np.random.uniform(20, 80, 60),
        'kdj_d': np.random.uniform(20, 80, 60),
        'kdj_j': np.random.uniform(20, 80, 60),
        'boll_upper': close + 0.5,
        'boll_mid': close,
        'boll_lower': close - 0.5,
        'boll_width': np.full(60, 0.05),
        'boll_percent': np.random.uniform(0, 100, 60),
        'ma5': close + np.random.randn(60) * 0.05,
        'ma10': close + np.random.randn(60) * 0.08,
        'ma20': close + np.random.randn(60) * 0.1,
        'ma60': close + np.random.randn(60) * 0.15,
    }, index=dates)
    return df


@pytest.fixture
def sample_signals():
    return {
        'macd': 'MACD金叉，偏多',
        'rsi': 'RSI 54，中性',
        'kdj': 'KDJ向上，偏多',
        'boll': '价格在中轨附近',
        'recommendation': '偏多信号',
    }


@pytest.fixture
def sample_snapshot(sample_data, sample_signals):
    from ai_analysis import build_indicator_snapshot
    return build_indicator_snapshot(sample_data, sample_signals, '000001', '平安银行')


# ============================================================
# TestBuildIndicatorSnapshot
# ============================================================

class TestBuildIndicatorSnapshot:

    def test_has_stock_name(self, sample_data, sample_signals):
        from ai_analysis import build_indicator_snapshot
        snap = build_indicator_snapshot(sample_data, sample_signals, '000001', '平安银行')
        assert '平安银行' in snap['股票']

    def test_has_symbol(self, sample_data, sample_signals):
        from ai_analysis import build_indicator_snapshot
        snap = build_indicator_snapshot(sample_data, sample_signals, '000001', '平安银行')
        assert '000001' in snap['股票']

    def test_has_price(self, sample_snapshot):
        assert isinstance(sample_snapshot['最新价'], float)

    def test_macd_fields_exist(self, sample_snapshot):
        macd = sample_snapshot['技术指标']['MACD']
        assert 'DIF' in macd
        assert 'DEA' in macd
        assert 'MACD柱' in macd

    def test_macd_two_decimals(self, sample_snapshot):
        macd = sample_snapshot['技术指标']['MACD']
        for key in ['DIF', 'DEA', 'MACD柱']:
            # 验证小数位数不超过2位（round效果）
            assert macd[key] == round(macd[key], 2)

    def test_rsi_multi_periods(self, sample_snapshot):
        rsi = sample_snapshot['技术指标']['RSI']
        assert 'RSI_6' in rsi
        assert 'RSI_12' in rsi
        assert 'RSI_24' in rsi

    def test_kdj_fields_exist(self, sample_snapshot):
        kdj = sample_snapshot['技术指标']['KDJ']
        assert 'K' in kdj
        assert 'D' in kdj
        assert 'J' in kdj

    def test_boll_fields_exist(self, sample_snapshot):
        boll = sample_snapshot['技术指标']['布林带']
        assert '上轨' in boll
        assert '中轨' in boll
        assert '下轨' in boll
        assert '带宽' in boll

    def test_ma_fields_when_present(self, sample_snapshot):
        ind = sample_snapshot['技术指标']
        for p in [5, 10, 20, 60]:
            assert f'MA{p}' in ind

    def test_signals_included(self, sample_snapshot, sample_signals):
        signals = sample_snapshot['交易信号']
        assert signals['MACD'] == sample_signals['macd']
        assert signals['综合建议'] == sample_signals['recommendation']

    def test_boll_bandwidth_format(self, sample_snapshot):
        bw = sample_snapshot['技术指标']['布林带']['带宽']
        assert isinstance(bw, str)
        assert '%' in bw

    # --- Edge cases ---

    def test_nan_indicators_handled(self):
        """NaN 指标值仍能被 round 处理"""
        from ai_analysis import build_indicator_snapshot
        dates = pd.date_range('2026-03-01', periods=5, freq='B')
        df = pd.DataFrame({
            'open': [10] * 5, 'high': [10.5] * 5, 'low': [9.5] * 5, 'close': [10] * 5,
            'volume': [1000000] * 5,
            'macd': [np.nan] * 5, 'macd_signal': [np.nan] * 5, 'macd_hist': [np.nan] * 5,
            'rsi_6': [np.nan] * 5, 'rsi_12': [np.nan] * 5, 'rsi_24': [np.nan] * 5,
            'kdj_k': [np.nan] * 5, 'kdj_d': [np.nan] * 5, 'kdj_j': [np.nan] * 5,
            'boll_upper': [np.nan] * 5, 'boll_mid': [np.nan] * 5, 'boll_lower': [np.nan] * 5,
            'boll_width': [np.nan] * 5, 'boll_percent': [np.nan] * 5,
        }, index=dates)
        signals = {'macd': '', 'rsi': '', 'kdj': '', 'boll': '', 'recommendation': ''}
        # 不抛异常即通过
        snap = build_indicator_snapshot(df, signals, '000001', '测试')
        assert '股票' in snap

    def test_missing_ma_columns_skipped(self):
        """没有 MA 列时不会崩溃"""
        from ai_analysis import build_indicator_snapshot
        dates = pd.date_range('2026-03-01', periods=5, freq='B')
        df = pd.DataFrame({
            'open': [10] * 5, 'high': [10.5] * 5, 'low': [9.5] * 5, 'close': [10] * 5,
            'volume': [1000000] * 5,
            'macd': [0.1] * 5, 'macd_signal': [0.05] * 5, 'macd_hist': [0.05] * 5,
            'rsi_6': [50] * 5, 'rsi_12': [50] * 5, 'rsi_24': [50] * 5,
            'kdj_k': [50] * 5, 'kdj_d': [50] * 5, 'kdj_j': [50] * 5,
            'boll_upper': [11] * 5, 'boll_mid': [10] * 5, 'boll_lower': [9] * 5,
            'boll_width': [0.1] * 5, 'boll_percent': [50] * 5,
        }, index=dates)
        signals = {'macd': '', 'rsi': '', 'kdj': '', 'boll': '', 'recommendation': ''}
        snap = build_indicator_snapshot(df, signals, '000001', '测试')
        # 无 ma5/10/20/60 列，不应出现这些 key
        ind = snap['技术指标']
        assert 'MA5' not in ind


# ============================================================
# TestBuildPrompt
# ============================================================

class TestBuildPrompt:

    def test_returns_string(self):
        from ai_analysis import _build_prompt
        prompt = _build_prompt({})
        assert isinstance(prompt, str)

    def test_contains_chinese(self):
        from ai_analysis import _build_prompt
        prompt = _build_prompt({})
        assert '技术' in prompt or '分析' in prompt or '指标' in prompt

    def test_mentions_json_format(self):
        from ai_analysis import _build_prompt
        prompt = _build_prompt({})
        assert 'json' in prompt.lower()
        assert '核心结论' in prompt


# ============================================================
# TestParseResponse
# ============================================================

class TestParseResponse:

    def test_bare_json(self):
        from ai_analysis import _parse_response
        raw = '{"核心结论": "走势偏强", "风险提示": [], "关键点位": {}, "操作参考": "持有"}'
        result = _parse_response(raw)
        assert result['核心结论'] == '走势偏强'

    def test_markdown_wrapped_json(self):
        from ai_analysis import _parse_response
        raw = '''```json
{"核心结论": "震荡整理", "风险提示": ["量能不足"], "关键点位": {"支撑": "10.5", "压力": "12.0"}, "操作参考": "观望"}
```'''
        result = _parse_response(raw)
        assert result['核心结论'] == '震荡整理'
        assert '量能不足' in result['风险提示'][0]
        assert result['关键点位']['支撑'] == '10.5'

    def test_json_with_extra_text(self):
        from ai_analysis import _parse_response
        raw = '分析结果：{"核心结论": "中性", "风险提示": [], "关键点位": {}, "操作参考": ""}仅供参考'
        result = _parse_response(raw)
        assert result['核心结论'] == '中性'

    def test_empty_string_returns_fallback(self):
        from ai_analysis import _parse_response
        result = _parse_response('')
        assert '格式异常' in result['核心结论']

    def test_non_json_text_returns_fallback(self):
        from ai_analysis import _parse_response
        result = _parse_response('这是一段纯文本分析，没有 JSON 结构')
        assert '格式异常' in result['核心结论']

    def test_missing_fields_get_defaults(self):
        from ai_analysis import _parse_response
        raw = '{"核心结论": "仅结论"}'
        result = _parse_response(raw)
        assert result['风险提示'] == []
        assert result['关键点位'] == {}
        assert result['操作参考'] == ''

    def test_missing_core_conclusion_gets_empty(self):
        from ai_analysis import _parse_response
        raw = '{"风险提示": ["test"]}'
        result = _parse_response(raw)
        assert result['核心结论'] == ''
        assert result['风险提示'] == ['test']

    def test_malformed_json_returns_fallback(self):
        from ai_analysis import _parse_response
        raw = '{"核心结论": "不完整'
        result = _parse_response(raw)
        assert '格式异常' in result['核心结论']


# ============================================================
# TestCallAIAnalysis
# ============================================================

class TestCallAIAnalysis:

    def test_successful_call(self, monkeypatch, sample_snapshot):
        from ai_analysis import call_ai_analysis

        class MockResponse:
            choices = [type('Choice', (), {'message': type('Msg', (), {'content': '{"核心结论": "看涨", "风险提示": [], "关键点位": {}, "操作参考": "买入"}'})()})()]

        import litellm
        monkeypatch.setattr(litellm, 'completion', lambda **kw: MockResponse())
        result = call_ai_analysis(sample_snapshot, 'openai/gpt-4', 'fake-key', None)
        assert result['核心结论'] == '看涨'

    def test_passes_model_params(self, monkeypatch, sample_snapshot):
        from ai_analysis import call_ai_analysis

        captured = {}

        class MockResponse:
            choices = [type('Choice', (), {'message': type('Msg', (), {'content': '{"核心结论": "ok", "风险提示": [], "关键点位": {}, "操作参考": ""}'})()})()]

        import litellm
        monkeypatch.setattr(litellm, 'completion', lambda **kw: (captured.update(kw), MockResponse())[1])
        call_ai_analysis(sample_snapshot, 'custom/model', 'key123', 'https://proxy.example.com', temperature=0.5)
        assert captured['model'] == 'custom/model'
        assert captured['api_key'] == 'key123'
        assert captured['temperature'] == 0.5

    def test_call_with_none_base_url(self, monkeypatch, sample_snapshot):
        from ai_analysis import call_ai_analysis

        class MockResponse:
            choices = [type('Choice', (), {'message': type('Msg', (), {'content': '{"核心结论": "ok", "风险提示": [], "关键点位": {}, "操作参考": ""}'})()})()]

        import litellm
        monkeypatch.setattr(litellm, 'completion', lambda **kw: MockResponse())
        result = call_ai_analysis(sample_snapshot, 'model', 'key', None)
        assert result['核心结论'] == 'ok'


# ============================================================
# TestIntegration
# ============================================================

class TestIntegration:

    def test_build_to_call_pipeline(self, monkeypatch, sample_data, sample_signals):
        """验证从 snapshot 构建到 AI 调用的完整链路"""
        from ai_analysis import build_indicator_snapshot, call_ai_analysis

        snap = build_indicator_snapshot(sample_data, sample_signals, '000001', '平安银行')
        assert snap['股票'] == '平安银行 (000001)'

        class MockResponse:
            choices = [type('Choice', (), {'message': type('Msg', (), {'content': '{"核心结论": "整体偏多", "风险提示": ["量能不足"], "关键点位": {"支撑": "10.0", "压力": "12.0"}, "操作参考": "持有"}'})()})()]

        import litellm
        monkeypatch.setattr(litellm, 'completion', lambda **kw: MockResponse())
        result = call_ai_analysis(snap, 'model', 'key', None)
        assert result['核心结论'] == '整体偏多'
        assert len(result['风险提示']) == 1
