from unittest.mock import MagicMock

import pandas as pd

from recommendation_modules import hot_stocks


def _raw(name, prev_close, price, volume):
    fields = [name] + ["0"] * 32
    fields[2] = str(prev_close)
    fields[3] = str(price)
    fields[8] = str(volume)
    return ",".join(fields)


def test_hot_stocks_cn_sorts_by_abs_change():
    response = MagicMock(status_code=200)
    response.text = "\n".join(
        [
            f'var hq_str_sz000001="{_raw("A", 10, 11, 1000)}";',
            f'var hq_str_sz000002="{_raw("B", 10, 9.5, 2000)}";',
        ]
    )
    requests_module = MagicMock()
    requests_module.get.return_value = response

    result = hot_stocks.hot_stocks_cn(
        [{"code": "000001"}, {"code": "000002"}],
        requests_module=requests_module,
        limit=2,
    )

    assert [item[hot_stocks.CODE] for item in result] == ["000001", "000002"]
    assert result[0][hot_stocks.CHANGE_PCT] == 10.0
    assert result[0][hot_stocks.HEAT_SCORE] == 10.0


class _Ticker:
    info = {"shortName": "Mock", "marketCap": 100}

    def __init__(self, symbol):
        self.symbol = symbol

    def history(self, period="5d"):
        return pd.DataFrame(
            {"Close": [10.0, 11.0], "Volume": [100, 200]},
            index=pd.date_range("2026-01-01", periods=2, freq="B"),
        )


class _YF:
    Ticker = _Ticker


def test_hot_stocks_hk_uses_yfinance_module():
    result = hot_stocks.hot_stocks_hk([{"code": "00700", "name": "腾讯控股"}], yf_module=_YF, limit=1)

    assert result[0][hot_stocks.CODE] == "00700"
    assert result[0][hot_stocks.CHANGE_PCT] == 10.0


def test_hot_stocks_us_sorts_by_volume():
    result = hot_stocks.hot_stocks_us(["AAPL"], yf_module=_YF, limit=1)

    assert result[0]["symbol"] == "AAPL"
    assert result[0]["change"] == 10.0
