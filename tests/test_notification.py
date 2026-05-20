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

class TestSendPush:

    def test_wechat_success(self):
        with patch("notification._send_wechat", return_value=True) as mock_wc, \
             patch("notification._send_feishu") as mock_fs:
            from notification import send_push
            results = send_push("test", "body", channels=["wechat"])
            assert results["wechat"] is True
            mock_wc.assert_called_once()
            mock_fs.assert_not_called()

    def test_feishu_success(self):
        with patch("notification._send_feishu", return_value=True) as mock_fs, \
             patch("notification._send_wechat") as mock_wc:
            from notification import send_push
            results = send_push("test", "body", channels=["feishu"])
            assert results["feishu"] is True
            mock_fs.assert_called_once()
            mock_wc.assert_not_called()

    def test_multiple_channels(self):
        with patch("notification._send_wechat", return_value=True), \
             patch("notification._send_feishu", return_value=True):
            from notification import send_push
            results = send_push("test", "body", channels=["wechat", "feishu"])
            assert len(results) == 2
            assert all(results.values())

    def test_unknown_channel(self):
        from notification import send_push
        results = send_push("test", "body", channels=["unknown"])
        assert results["unknown"] is False

    def test_channel_exception(self):
        with patch("notification._send_wechat", side_effect=Exception("boom")):
            from notification import send_push
            results = send_push("test", "body", channels=["wechat"])
            assert results["wechat"] is False

    def test_strips_whitespace(self):
        with patch("notification._send_wechat", return_value=True) as mock_wc:
            from notification import send_push
            send_push("test", "body", channels=["  wechat  "])
            mock_wc.assert_called_once()


# ============================================================
# TestWechatSender
# ============================================================

class TestWechatSender:

    def test_missing_url_returns_false(self):
        with patch("notification.WECHAT_WEBHOOK_URL", ""):
            from notification import _send_wechat
            assert _send_wechat("t", "b") is False

    def test_success_response(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"errcode": 0}
        with patch("notification.WECHAT_WEBHOOK_URL", "https://example.com/webhook"), \
             patch("requests.post", return_value=mock_resp) as mock_post:
            from notification import _send_wechat
            result = _send_wechat("title", "body")
            assert result is True
            mock_post.assert_called_once()
            payload = mock_post.call_args[1]["json"]
            assert payload["msgtype"] == "markdown"
            assert "## title" in payload["markdown"]["content"]

    def test_errcode_nonzero(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"errcode": 1, "errmsg": "error"}
        with patch("notification.WECHAT_WEBHOOK_URL", "https://example.com/webhook"), \
             patch("requests.post", return_value=mock_resp):
            from notification import _send_wechat
            assert _send_wechat("t", "b") is False

    def test_http_error(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("notification.WECHAT_WEBHOOK_URL", "https://example.com/webhook"), \
             patch("requests.post", return_value=mock_resp):
            from notification import _send_wechat
            assert _send_wechat("t", "b") is False


# ============================================================
# TestFeishuSender
# ============================================================

class TestFeishuSender:

    def test_missing_url_returns_false(self):
        with patch("notification.FEISHU_WEBHOOK_URL", ""):
            from notification import _send_feishu
            assert _send_feishu("t", "b") is False

    def test_success_response(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 0}
        with patch("notification.FEISHU_WEBHOOK_URL", "https://open.feishu.cn/hook/xxx"), \
             patch("requests.post", return_value=mock_resp) as mock_post:
            from notification import _send_feishu
            result = _send_feishu("title", "body")
            assert result is True
            payload = mock_post.call_args[1]["json"]
            assert payload["msg_type"] == "interactive"
            assert payload["card"]["header"]["title"]["content"] == "title"
            assert payload["card"]["elements"][0]["content"] == "body"

    def test_feishu_long_markdown_is_chunked(self):
        from notification import _build_feishu_markdown_elements

        elements = _build_feishu_markdown_elements("A" * 3600 + "\n\nB" * 100, max_chars=1000)

        assert len(elements) > 1
        assert all(item["tag"] == "markdown" for item in elements)
        assert all(len(item["content"]) <= 1000 for item in elements)

    def test_error_code(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 1, "msg": "error"}
        with patch("notification.FEISHU_WEBHOOK_URL", "https://open.feishu.cn/hook/xxx"), \
             patch("requests.post", return_value=mock_resp):
            from notification import _send_feishu
            assert _send_feishu("t", "b") is False

    def test_http_error(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("notification.FEISHU_WEBHOOK_URL", "https://open.feishu.cn/hook/xxx"), \
             patch("requests.post", return_value=mock_resp):
            from notification import _send_feishu
            assert _send_feishu("t", "b") is False
