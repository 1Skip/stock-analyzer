from data.providers.sina_intraday_provider import SinaIntradayProvider


class _Response:
    status_code = 200

    def json(self):
        return [{
            "day": "2026-06-04 09:35:00",
            "open": "10.00",
            "high": "10.20",
            "low": "9.90",
            "close": "10.10",
            "volume": "1200",
            "amount": "1212000",
        }]


class _Session:
    def __init__(self):
        self.urls = []

    def get(self, url, timeout=None):
        self.urls.append((url, timeout))
        return _Response()


def test_sina_intraday_provider_builds_symbol_and_raw_frame():
    session = _Session()
    provider = SinaIntradayProvider(session)

    frame = provider.fetch_raw("601012")

    assert "symbol=sh601012" in session.urls[0][0]
    assert session.urls[0][1] == 10
    assert list(frame.columns) == ["time", "open", "high", "low", "close", "volume", "amount"]
    assert frame.iloc[0]["time"] == "2026-06-04 09:35:00"


def test_sina_intraday_provider_uses_sz_for_non_sh_codes():
    assert SinaIntradayProvider.sina_symbol("000001") == "sz000001"
    assert SinaIntradayProvider.sina_symbol("300750") == "sz300750"
