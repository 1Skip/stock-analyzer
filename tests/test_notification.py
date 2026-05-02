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


# ============================================================
# TestSendPush
# ============================================================

class TestSendPush:

    def test_wechat_success(self):
        with patch("notification._send_wechat", return_value=True) as mock_wc, \
             patch("notification._send_telegram") as mock_tg:
            from notification import send_push
            results = send_push("test", "body", channels=["wechat"])
            assert results["wechat"] is True
            mock_wc.assert_called_once()
            mock_tg.assert_not_called()

    def test_telegram_success(self):
        with patch("notification._send_telegram", return_value=True) as mock_tg, \
             patch("notification._send_wechat") as mock_wc:
            from notification import send_push
            results = send_push("test", "body", channels=["telegram"])
            assert results["telegram"] is True
            mock_tg.assert_called_once()
            mock_wc.assert_not_called()

    def test_bark_success(self):
        with patch("notification._send_bark", return_value=True) as mock_bark:
            from notification import send_push
            results = send_push("test", "body", channels=["bark"])
            assert results["bark"] is True
            mock_bark.assert_called_once()

    def test_multiple_channels(self):
        with patch("notification._send_wechat", return_value=True), \
             patch("notification._send_telegram", return_value=True), \
             patch("notification._send_bark", return_value=True):
            from notification import send_push
            results = send_push("test", "body", channels=["wechat", "telegram", "bark"])
            assert len(results) == 3
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
# TestTelegramSender
# ============================================================

class TestTelegramSender:

    def test_missing_config_returns_false(self):
        with patch("notification.TELEGRAM_BOT_TOKEN", ""), \
             patch("notification.TELEGRAM_CHAT_ID", ""):
            from notification import _send_telegram
            assert _send_telegram("t", "b") is False

    def test_success_response(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True}
        with patch("notification.TELEGRAM_BOT_TOKEN", "123:abc"), \
             patch("notification.TELEGRAM_CHAT_ID", "456"), \
             patch("requests.post", return_value=mock_resp) as mock_post:
            from notification import _send_telegram
            result = _send_telegram("title", "body")
            assert result is True
            payload = mock_post.call_args[1]["json"]
            assert payload["parse_mode"] == "HTML"
            assert "title" in payload["text"]

    def test_ok_false(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": False}
        with patch("notification.TELEGRAM_BOT_TOKEN", "123:abc"), \
             patch("notification.TELEGRAM_CHAT_ID", "456"), \
             patch("requests.post", return_value=mock_resp):
            from notification import _send_telegram
            assert _send_telegram("t", "b") is False


# ============================================================
# TestBarkSender
# ============================================================

class TestBarkSender:

    def test_missing_url_returns_false(self):
        with patch("notification.BARK_URL", ""):
            from notification import _send_bark
            assert _send_bark("t", "b") is False

    def test_success_response(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("notification.BARK_URL", "https://api.day.app/xxx"), \
             patch("requests.post", return_value=mock_resp) as mock_post:
            from notification import _send_bark
            result = _send_bark("title", "body")
            assert result is True
            payload = mock_post.call_args[1]["json"]
            assert payload["title"] == "title"
            assert payload["body"] == "body"

    def test_http_error(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        with patch("notification.BARK_URL", "https://api.day.app/xxx"), \
             patch("requests.post", return_value=mock_resp):
            from notification import _send_bark
            assert _send_bark("t", "b") is False


# ============================================================
# TestPushPlusSender
# ============================================================

class TestPushPlusSender:

    def test_missing_token_returns_false(self):
        with patch("notification.PUSHPLUS_TOKEN", ""):
            from notification import _send_pushplus
            assert _send_pushplus("t", "b") is False

    def test_success_response(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 200}
        with patch("notification.PUSHPLUS_TOKEN", "test_token"), \
             patch("requests.post", return_value=mock_resp) as mock_post:
            from notification import _send_pushplus
            result = _send_pushplus("title", "body")
            assert result is True
            payload = mock_post.call_args[1]["json"]
            assert payload["token"] == "test_token"
            assert payload["template"] == "markdown"

    def test_error_code(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 500, "msg": "error"}
        with patch("notification.PUSHPLUS_TOKEN", "test_token"), \
             patch("requests.post", return_value=mock_resp):
            from notification import _send_pushplus
            assert _send_pushplus("t", "b") is False

    def test_http_error(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("notification.PUSHPLUS_TOKEN", "test_token"), \
             patch("requests.post", return_value=mock_resp):
            from notification import _send_pushplus
            assert _send_pushplus("t", "b") is False
