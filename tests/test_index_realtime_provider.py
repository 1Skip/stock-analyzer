from data.providers.index_realtime_provider import SinaIndexRealtimeProvider


class _Response:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


class _Session:
    def __init__(self, response):
        self.response = response
        self.urls = []

    def get(self, url, headers=None, timeout=None):
        self.urls.append((url, timeout))
        return self.response


def test_sina_index_code_prefixes():
    assert SinaIndexRealtimeProvider.sina_code("000001") == "sh000001"
    assert SinaIndexRealtimeProvider.sina_code("600519") == "sh600519"
    assert SinaIndexRealtimeProvider.sina_code("899050") == "bj899050"
    assert SinaIndexRealtimeProvider.sina_code("399001") == "sz399001"


def test_sina_index_fetch_quote_parses_legacy_fields():
    session = _Session(_Response('"上证指数,3341.44,3341.44,3365.82,3370.00,3335.00"'))
    provider = SinaIndexRealtimeProvider(session)

    result = provider.fetch_quote("000001", timeout=2)

    assert "sh000001" in session.urls[0][0]
    assert session.urls[0][1] == 2
    assert result["symbol"] == "000001"
    assert result["name"] == "上证指数"
    assert result["price"] == 3365.82
    assert abs(result["change_pct"] - 0.73) < 0.01
    assert result["prev_close"] == 3341.44


def test_sina_index_parse_short_payload_returns_none():
    assert SinaIndexRealtimeProvider.parse_quote("000001", "上证指数,3300") is None
