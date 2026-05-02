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
        assert signals['RSI'] == sample_signals['rsi']
        assert signals['KDJ'] == sample_signals['kdj']
        assert signals['布林带'] == sample_signals['boll']
        # "综合建议" 已从 snapshot 移除，AI 应独立分析不依赖系统信号

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


# ============================================================
# TestAgentProtocols
# ============================================================

class TestAgentProtocols:

    def test_agent_config_defaults(self):
        from agent_protocols import AgentConfig
        cfg = AgentConfig(name="测试")
        assert cfg.name == "测试"
        assert cfg.model == ""
        assert cfg.temperature == 0.2
        assert cfg.max_tokens == 512
        assert cfg.timeout == 30

    def test_agent_config_clone(self):
        from agent_protocols import AgentConfig
        cfg = AgentConfig(name="原")
        cloned = cfg.clone(name="新", temperature=0.5)
        assert cloned.name == "新"
        assert cloned.temperature == 0.5
        assert cloned.model == ""
        assert cfg.name == "原"

    def test_agent_result_defaults(self):
        from agent_protocols import AgentResult
        r = AgentResult(agent="test", content="", success=True)
        assert r.structured == {}
        assert r.error == ""

    def test_agent_result_with_structured(self):
        from agent_protocols import AgentResult
        r = AgentResult(agent="test", content="raw", success=True,
                        structured={"key": "val"}, error="oops")
        assert r.structured["key"] == "val"
        assert r.error == "oops"

    def test_agent_context_config_for(self):
        from agent_protocols import AgentContext
        ctx = AgentContext(snapshot={}, api_key="k", model="m")
        cfg = ctx.config_for("技术分析", max_tokens=300)
        assert cfg.name == "技术分析"
        assert cfg.model == "m"
        assert cfg.max_tokens == 300


# ============================================================
# TestCallAgent
# ============================================================

class TestCallAgent:

    def test_successful_call(self, monkeypatch, sample_snapshot):
        from ai_analysis import _call_agent
        from agent_protocols import AgentConfig

        class MockResponse:
            choices = [type('Choice', (), {'message': type('Msg', (), {
                'content': '{"MACD解读": "金叉形成", "RSI解读": "中性", "KDJ解读": "向上", "布林带解读": "中轨附近", "均线解读": "多头排列", "指标一致性": "一致偏多"}'
            })()})()]

        import litellm
        monkeypatch.setattr(litellm, 'completion', lambda **kw: MockResponse())
        cfg = AgentConfig(name="技术分析", model="test-model")
        result = _call_agent("系统提示词", sample_snapshot, cfg, "key", None)
        assert result["agent"] == "技术分析"
        assert result["success"] is True
        assert result["structured"]["MACD解读"] == "金叉形成"
        assert result["error"] == ""

    def test_exception_returns_error(self, monkeypatch, sample_snapshot):
        from ai_analysis import _call_agent
        from agent_protocols import AgentConfig

        import litellm
        monkeypatch.setattr(litellm, 'completion', lambda **kw: (_ for _ in ()).throw(Exception("网络超时")))
        cfg = AgentConfig(name="风险评估", model="test-model")
        result = _call_agent("系统提示词", sample_snapshot, cfg, "key", None)
        assert result["agent"] == "风险评估"
        assert result["success"] is False
        assert "网络超时" in result["error"]
        assert result["content"] == ""

    def test_passes_agent_config_params(self, monkeypatch, sample_snapshot):
        from ai_analysis import _call_agent
        from agent_protocols import AgentConfig

        captured = {}

        class MockResponse:
            choices = [type('Choice', (), {'message': type('Msg', (), {
                'content': '{"风险等级": "中", "风险因素": [], "矛盾信号": "", "关注点位": {}}'
            })()})()]

        import litellm
        monkeypatch.setattr(litellm, 'completion', lambda **kw: (captured.update(kw), MockResponse())[1])
        cfg = AgentConfig(name="风险评估", model="custom/model", temperature=0.3, max_tokens=256, timeout=15)
        _call_agent("提示词", sample_snapshot, cfg, "api-key-123", "https://proxy.example.com")
        assert captured["model"] == "custom/model"
        assert captured["api_key"] == "api-key-123"
        assert captured["temperature"] == 0.3
        assert captured["max_tokens"] == 256
        assert captured["timeout"] == 15


# ============================================================
# TestMultiAgentPrompts
# ============================================================

class TestMultiAgentPrompts:

    def test_technical_prompt_exists(self):
        from ai_analysis import _TECHNICAL_PROMPT
        assert isinstance(_TECHNICAL_PROMPT, str)
        assert len(_TECHNICAL_PROMPT) > 50
        assert "技术指标" in _TECHNICAL_PROMPT

    def test_risk_prompt_exists(self):
        from ai_analysis import _RISK_PROMPT
        assert isinstance(_RISK_PROMPT, str)
        assert len(_RISK_PROMPT) > 50
        assert "风险" in _RISK_PROMPT

    def test_decision_prompt_exists(self):
        from ai_analysis import _DECISION_PROMPT
        assert isinstance(_DECISION_PROMPT, str)
        assert len(_DECISION_PROMPT) > 50
        assert "决策" in _DECISION_PROMPT

    def test_technical_prompt_requires_json(self):
        from ai_analysis import _TECHNICAL_PROMPT
        assert "json" in _TECHNICAL_PROMPT.lower()

    def test_risk_prompt_requires_json(self):
        from ai_analysis import _RISK_PROMPT
        assert "json" in _RISK_PROMPT.lower()

    def test_decision_prompt_requires_json(self):
        from ai_analysis import _DECISION_PROMPT
        assert "json" in _DECISION_PROMPT.lower()


# ============================================================
# TestRunMultiAgentAnalysis
# ============================================================

class TestRunMultiAgentAnalysis:

    @pytest.fixture
    def mock_agents(self, monkeypatch):
        """Mock _call_agent 返回预设结果"""

        def _mock(agents_results):
            def mock_call(system_prompt, snapshot, config, api_key, base_url):
                name = config.name
                if name in agents_results:
                    return agents_results[name]
                return {"agent": name, "content": "", "success": False, "structured": {}, "error": "未预设"}
            monkeypatch.setattr("ai_analysis._call_agent", mock_call)
        return _mock

    def test_full_pipeline(self, sample_snapshot, mock_agents):
        from ai_analysis import run_multi_agent_analysis

        mock_agents({
            "技术分析": {
                "agent": "技术分析", "content": "t", "success": True,
                "structured": {"MACD解读": "多头", "RSI解读": "中性", "KDJ解读": "向上",
                               "布林带解读": "中轨", "均线解读": "多头排列", "指标一致性": "一致偏多"},
                "error": "",
            },
            "风险评估": {
                "agent": "风险评估", "content": "r", "success": True,
                "structured": {"风险等级": "中", "风险因素": ["超买"], "矛盾信号": "MACD多但RSI高",
                               "关注点位": {"下方": "10.0", "上方": "12.0"}},
                "error": "",
            },
            "决策综合": {
                "agent": "决策综合", "content": "d", "success": True,
                "structured": {"核心结论": "偏多但需谨慎", "技术面评分": "偏多", "信心度": "中",
                               "操作参考": "支撑位附近可关注", "关注要点": ["量能", "RSI"]},
                "error": "",
            },
        })

        output = run_multi_agent_analysis(sample_snapshot, "model", "key", "")
        assert output["mode"] == "multi_agent"

        tech = output["technical"]
        assert tech["success"] is True
        assert tech["structured"]["MACD解读"] == "多头"

        risk = output["risk"]
        assert risk["success"] is True
        assert risk["structured"]["风险等级"] == "中"

        decision = output["decision"]
        assert decision["success"] is True
        assert decision["structured"]["核心结论"] == "偏多但需谨慎"

    def test_technical_failure_propagates(self, sample_snapshot, mock_agents):
        from ai_analysis import run_multi_agent_analysis

        mock_agents({
            "技术分析": {
                "agent": "技术分析", "content": "", "success": False,
                "structured": {}, "error": "API 超时",
            },
            "风险评估": {
                "agent": "风险评估", "content": "r", "success": True,
                "structured": {"风险等级": "低", "风险因素": [], "矛盾信号": "", "关注点位": {}},
                "error": "",
            },
            "决策综合": {
                "agent": "决策综合", "content": "d", "success": True,
                "structured": {"核心结论": "观望", "技术面评分": "中性", "信心度": "低",
                               "操作参考": "", "关注要点": []},
                "error": "",
            },
        })

        output = run_multi_agent_analysis(sample_snapshot, "model", "key", "")
        assert output["technical"]["success"] is False
        assert output["technical"]["error"] == "API 超时"
        assert output["risk"]["success"] is True
        # 决策应该仍然完成（使用部分数据）
        assert output["decision"]["success"] is True

    def test_decision_still_runs_when_risk_fails(self, sample_snapshot, mock_agents):
        from ai_analysis import run_multi_agent_analysis

        mock_agents({
            "技术分析": {
                "agent": "技术分析", "content": "t", "success": True,
                "structured": {"MACD解读": "多头", "RSI解读": "中性", "KDJ解读": "向上",
                               "布林带解读": "中轨", "均线解读": "多头", "指标一致性": "一致"},
                "error": "",
            },
            "风险评估": {
                "agent": "风险评估", "content": "", "success": False,
                "structured": {}, "error": "服务不可用",
            },
            "决策综合": {
                "agent": "决策综合", "content": "", "success": False,
                "structured": {}, "error": "数据不足",
            },
        })

        output = run_multi_agent_analysis(sample_snapshot, "model", "key", "")
        assert output["risk"]["success"] is False
        assert output["risk"]["error"] == "服务不可用"

    def test_output_structure_keys(self, sample_snapshot, mock_agents):
        from ai_analysis import run_multi_agent_analysis

        mock_agents({
            "技术分析": {
                "agent": "技术分析", "content": "", "success": True,
                "structured": {"MACD解读": "", "RSI解读": "", "KDJ解读": "",
                               "布林带解读": "", "均线解读": "", "指标一致性": ""},
                "error": "",
            },
            "风险评估": {
                "agent": "风险评估", "content": "", "success": True,
                "structured": {"风险等级": "", "风险因素": [], "矛盾信号": "", "关注点位": {}},
                "error": "",
            },
            "决策综合": {
                "agent": "决策综合", "content": "", "success": True,
                "structured": {"核心结论": "", "技术面评分": "", "信心度": "", "操作参考": "", "关注要点": []},
                "error": "",
            },
        })

        output = run_multi_agent_analysis(sample_snapshot, "model", "key", "")
        for key in ["technical", "risk", "decision", "mode"]:
            assert key in output, f"缺少 key: {key}"
        assert output["mode"] == "multi_agent"
