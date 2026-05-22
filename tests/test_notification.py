"""通知推送模块测试"""
import pytest
from unittest.mock import patch, MagicMock


# ============================================================
# TestBuildAnalysisReport
# ============================================================

class TestBuildAnalysisReport:

    def test_positive_change(self):
        from notification import build_analysis_report
        signals = {"macd": "偏多", "rsi": "偏多", "kdj": "观望", "boll": "偏多"}
        title, body = build_analysis_report(
            "000001", "平安银行", 12.50, 2.35, signals
        )
        assert "平安银行" in title
        assert "000001" in title
        assert "12.50" in title
        assert "📈" in title
        assert "+2.35%" in title
        assert "12.50" in body
        assert "macd" in body
        assert "🟢" in body

    def test_negative_change(self):
        from notification import build_analysis_report
        signals = {"macd": "偏空", "rsi": "偏空", "kdj": "偏空", "boll": "偏空"}
        title, body = build_analysis_report(
            "AAPL", "Apple", 150.00, -3.50, signals
        )
        assert "📉" in title
        assert "-3.50%" in title
        assert "🔴" in body

    def test_zero_change(self):
        from notification import build_analysis_report
        signals = {"macd": "观望", "rsi": "观望"}
        title, body = build_analysis_report(
            "000001", "平安银行", 10.00, 0.00, signals
        )
        assert "➡" in title
        assert "+0.00%" in title

    def test_with_ai_summary(self):
        from notification import build_analysis_report
        signals = {"macd": "偏多"}
        summary = "MACD金叉形成，短期看涨"
        title, body = build_analysis_report(
            "000001", "平安银行", 10.00, 1.00, signals,
            ai_summary=summary
        )
        assert "AI解读" in body
        assert summary in body

    def test_without_ai_summary(self):
        from notification import build_analysis_report
        signals = {"macd": "偏多"}
        title, body = build_analysis_report(
            "000001", "平安银行", 10.00, 1.00, signals
        )
        assert "AI解读" not in body

    def test_analysis_report_includes_main_accumulation(self):
        from notification import build_analysis_report

        _, body = build_analysis_report(
            "000001",
            "平安银行",
            10.00,
            1.00,
            {"recommendation": "偏多"},
            indicators={
                "main_accumulation": 3.21,
                "accumulation_risk": 42,
                "accumulation_trend": 55.6,
            },
        )

        assert "主力吸货" in body
        assert "吸货 3.21" in body
        assert "风险 42.00" in body
        assert "真实日K推导" in body

    def test_with_trade_plan_and_defense_dashboard(self):
        from notification import build_analysis_report

        decision = {
            "score": 72,
            "confidence": 76,
            "risk_level": "中",
            "action": "轻仓试探",
            "position": "1-2成",
            "recommendation": "偏多信号",
            "key_levels": {
                "price": 10.0,
                "support": 9.5,
                "mid": 10.2,
                "resistance": 11.0,
                "ma20": 10.1,
            },
            "risk_alerts": [],
        }

        _, body = build_analysis_report(
            "000001",
            "平安银行",
            10.0,
            1.0,
            {"recommendation": "偏多"},
            decision=decision,
            extended_info={"fund_flow": {"main_net_inflow": 1000000, "main_net_inflow_ratio": 1.2}},
        )

        assert "交易计划卡片" in body
        assert "风控防御看板" in body
        assert "资金博弈溯源" in body
        assert "数据说明" in body


# ============================================================
# TestSendPush
# ============================================================
