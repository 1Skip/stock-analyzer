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


# ============================================================
# TestBuildSectorReport
# ============================================================

class TestBuildSectorReport:

    def _make_sector_data(self):
        return {
            "苹果概念": {
                "短线": [
                    {'symbol': '002475', 'name': '立讯精密', 'latest_price': 35.20, 'change_pct': 2.1, 'strategy': '短线'},
                    {'symbol': '002241', 'name': '歌尔股份', 'latest_price': 22.15, 'change_pct': 1.8, 'strategy': '短线'},
                ],
                "长线": [
                    {'symbol': '603501', 'name': '韦尔股份', 'latest_price': 95.30, 'change_pct': 0.5, 'strategy': '长线'},
                ],
            },
            "电力": {
                "短线": [
                    {'symbol': '600900', 'name': '长江电力', 'latest_price': 22.50, 'change_pct': 0.0, 'strategy': '短线'},
                ],
                "长线": [
                    {'symbol': '601985', 'name': '中国核电', 'latest_price': 8.20, 'change_pct': 1.2, 'strategy': '长线'},
                    {'symbol': '600011', 'name': '华能国际', 'latest_price': 7.80, 'change_pct': -0.8, 'strategy': '长线'},
                ],
            },
            "特斯拉概念": {"短线": [], "长线": []},
            "算力租赁": {"短线": [], "长线": []},
        }

    def test_returns_title_and_body(self):
        from notification import build_sector_report
        data = self._make_sector_data()
        title, body = build_sector_report(data)
        assert "板块龙头推荐" in title
        assert len(body) > 0

    def test_includes_sector_names(self):
        from notification import build_sector_report
        data = self._make_sector_data()
        title, body = build_sector_report(data)
        assert "苹果概念" in body
        assert "电力" in body

    def test_includes_strategy_labels(self):
        from notification import build_sector_report
        data = self._make_sector_data()
        title, body = build_sector_report(data)
        assert "短线" in body
        assert "长线" in body

    def test_includes_stock_info(self):
        from notification import build_sector_report
        data = self._make_sector_data()
        title, body = build_sector_report(data)
        assert "立讯精密" in body
        assert "002475" in body
        assert "35.20" in body

    def test_positive_change_shows_up_arrow(self):
        from notification import build_sector_report
        data = self._make_sector_data()
        title, body = build_sector_report(data)
        assert "📈" in body

    def test_negative_change_shows_down_arrow(self):
        from notification import build_sector_report
        data = self._make_sector_data()
        title, body = build_sector_report(data)
        assert "📉" in body

    def test_zero_change_shows_neutral(self):
        from notification import build_sector_report
        data = self._make_sector_data()
        title, body = build_sector_report(data)
        assert "➡" in body

    def test_empty_sector_shows_no_recommendation(self):
        from notification import build_sector_report
        data = self._make_sector_data()
        title, body = build_sector_report(data)
        assert "暂无推荐" in body

    def test_empty_data_still_returns_valid(self):
        from notification import build_sector_report
        title, body = build_sector_report({})
        assert "板块龙头推荐" in title
        assert isinstance(body, str)
