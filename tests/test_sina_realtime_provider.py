from data.providers.sina_realtime_provider import SinaRealtimeProvider


class _Response:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def get(self, url, headers=None, timeout=None):
        self.urls.append((url, headers, timeout))
        return self.responses.pop(0)


def _cn_raw():
    fields = ["平安银行"] + ["0"] * 32
    fields[1] = "12.30"
    fields[2] = "12.00"
    fields[3] = "12.50"
    fields[4] = "12.60"
    fields[5] = "12.20"
    fields[8] = "50000000"
    fields[30] = "2026-06-04"
    fields[31] = "14:59:59"
    return ",".join(fields)


def test_cn_code_prefixes():
    assert SinaRealtimeProvider.cn_code("600519") == "sh600519"
    assert SinaRealtimeProvider.cn_code("000001") == "sz000001"
    assert SinaRealtimeProvider.cn_code("300750") == "sz300750"
    assert SinaRealtimeProvider.cn_code("899050") == "bj899050"


def test_fetch_cn_quote_matches_legacy_fields():
    session = _Session([_Response(f'var hq_str_sz000001="{_cn_raw()}";')])
    provider = SinaRealtimeProvider(session)

    quote = provider.fetch_cn_quote("000001")

    assert quote["symbol"] == "000001"
    assert quote["price"] == 12.50
    assert quote["volume"] == 500000
    assert quote["volume_unit"] == "hand"
    assert quote["quote_date"] == "2026-06-04"
    assert quote["quote_time"] == "14:59:59"
    assert round(quote["change"], 2) == 4.17


def test_fetch_cn_batch_quotes_adds_change_pct():
    session = _Session([_Response(f'var hq_str_sz000001="{_cn_raw()}";')])
    provider = SinaRealtimeProvider(session)

    result = provider.fetch_cn_batch_quotes(["000001"])

    assert result["000001"]["price"] == 12.50
    assert result["000001"]["change_pct"] == 4.17


def test_fetch_cn_name_returns_first_field():
    session = _Session([_Response('var hq_str_sz000001="平安银行,1,2,3";')])
    provider = SinaRealtimeProvider(session)

    assert provider.fetch_cn_name("000001") == "平安银行"


def test_parse_hk_and_us_quotes():
    hk_raw = "腾讯控股,TENCENT,390.0,388.0,389.5,385.0,382.0,0,1.2,0,0,0,1234567,0,0,0,0"
    us_raw = "Apple,200.0,1.5,14:59,3.0,198.0,201.0,197.0,0,0,9876543"

    hk = SinaRealtimeProvider.parse_global_quote("00700", hk_raw, "hk")
    us = SinaRealtimeProvider.parse_global_quote("AAPL", us_raw, "us")

    assert hk["price"] == 389.5
    assert hk["prev_close"] == 385.0
    assert us["price"] == 200.0
    assert us["prev_close"] == 197.0
