import pandas as pd

from data.providers.eastmoney_realtime_provider import EastmoneyRealtimeProvider
from data.providers.tencent_realtime_provider import TencentRealtimeProvider


def _safe_float(value):
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


class _Ak:
    def stock_zh_a_spot_em(self):
        return pd.DataFrame([{
            "代码": "002001",
            "名称": "测试股",
            "最新价": 10.2,
            "涨跌幅": 1.2,
            "今开": 10.0,
            "昨收": 10.08,
            "最高": 10.3,
            "最低": 9.9,
            "成交量": 123456,
            "换手率": 2.5,
            "总市值": 20_000_000_000,
        }])


class _Response:
    status_code = 200

    text = ""


class _Requests:
    def __init__(self, text):
        self.text = text
        self.urls = []

    def get(self, url, headers=None, timeout=None):
        self.urls.append((url, timeout))
        response = _Response()
        response.text = self.text
        return response


def test_eastmoney_realtime_provider_maps_spot_fields():
    provider = EastmoneyRealtimeProvider(_Ak(), _safe_float)

    result = provider.fetch_batch(["002001"])

    quote = result["002001"]
    assert quote["name"] == "测试股"
    assert quote["price"] == 10.2
    assert quote["change_pct"] == 1.2
    assert quote["source"] == "东方财富实时行情"


def test_tencent_realtime_provider_prefix_and_fields():
    parts = [""] * 46
    parts[1] = "测试股"
    parts[2] = "sz002001"
    parts[3] = "10.4"
    parts[4] = "10.0"
    parts[5] = "10.1"
    parts[6] = "120000"
    parts[32] = "4.0"
    parts[33] = "10.5"
    parts[34] = "9.9"
    parts[38] = "2.1"
    parts[45] = "200"
    requests = _Requests('v_sz002001="' + "~".join(parts) + '";')
    provider = TencentRealtimeProvider(requests, _safe_float)

    result = provider.fetch_batch(["002001"])

    assert "sz002001" in requests.urls[0][0]
    quote = result["002001"]
    assert quote["price"] == 10.4
    assert quote["change_pct"] == 4.0
    assert quote["market_cap"] == 20_000_000_000
    assert quote["source"] == "腾讯行情"


def test_tencent_code_prefixes():
    assert TencentRealtimeProvider.tencent_code("600519") == "sh600519"
    assert TencentRealtimeProvider.tencent_code("002001") == "sz002001"
    assert TencentRealtimeProvider.tencent_code("899050") == "bj899050"
