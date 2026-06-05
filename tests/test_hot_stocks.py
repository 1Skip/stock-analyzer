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


class _EmptyTicker:
    info = {}

    def __init__(self, symbol):
        self.symbol = symbol

    def history(self, period="5d"):
        return pd.DataFrame()


class _EmptyYF:
    Ticker = _EmptyTicker


class _SinaProvider:
    def __init__(self, quotes):
        self.quotes = quotes

    def fetch_global_quote(self, symbol, market):
        return self.quotes.get((market, symbol))


class _AkHKHotRank:
    @staticmethod
    def stock_hk_hot_rank_em():
        return pd.DataFrame(
            [
                {"代码": "700", "股票名称": "Tencent", "最新价": 400.0, "涨跌幅": 2.5},
                {"代码": "981", "股票名称": "SMIC", "最新价": 80.0, "涨跌幅": -3.0},
            ]
        )


def test_hot_stocks_hk_uses_yfinance_module():
    result = hot_stocks.hot_stocks_hk(
        [{"code": "00700", "name": "腾讯控股"}],
        yf_module=_YF,
        eastmoney_provider=False,
        limit=1,
    )

    assert result[0][hot_stocks.CODE] == "00700"
    assert result[0][hot_stocks.CHANGE_PCT] == 10.0


def test_hot_stocks_hk_prefers_eastmoney_hot_rank():
    result = hot_stocks.hot_stocks_hk(
        [{"code": "00700", "name": "Tencent"}],
        yf_module=_EmptyYF,
        eastmoney_provider=lambda limit: [
            {
                hot_stocks.CODE: "00700",
                hot_stocks.NAME: "Tencent",
                hot_stocks.LATEST_PRICE: 400.0,
                hot_stocks.CHANGE_PCT: 2.5,
                "source": "东方财富港股人气榜",
            },
            {
                hot_stocks.CODE: "00981",
                hot_stocks.NAME: "SMIC",
                hot_stocks.LATEST_PRICE: 80.0,
                hot_stocks.CHANGE_PCT: -3.0,
                "source": "东方财富港股人气榜",
            },
        ][:limit],
        limit=2,
    )

    assert [item[hot_stocks.CODE] for item in result] == ["00700", "00981"]
    assert result[0][hot_stocks.CHANGE_PCT] == 2.5
    assert result[0]["source"] == "东方财富港股人气榜"


def test_hot_stocks_us_sorts_by_volume():
    result = hot_stocks.hot_stocks_us(["AAPL"], yf_module=_YF, limit=1)

    assert result[0]["symbol"] == "AAPL"
    assert result[0]["change"] == 10.0


def test_hot_stocks_hk_falls_back_to_sina_when_yfinance_empty():
    provider = _SinaProvider(
        {
            ("hk", "00700"): {
                "name": "Tencent",
                "price": 400.0,
                "change": 2.5,
                "volume": 1000,
            }
        }
    )

    result = hot_stocks.hot_stocks_hk(
        [{"code": "00700", "name": "Tencent"}],
        yf_module=_EmptyYF,
        sina_provider=provider,
        eastmoney_provider=False,
        limit=1,
    )

    assert result[0][hot_stocks.CODE] == "00700"
    assert result[0][hot_stocks.CHANGE_PCT] == 2.5
    assert result[0]["source"] == "新浪财经"


def test_hot_stocks_us_falls_back_to_sina_when_yfinance_empty():
    provider = _SinaProvider(
        {
            ("us", "AAPL"): {
                "name": "Apple",
                "price": 200.0,
                "change": -1.25,
                "volume": 3000,
            }
        }
    )

    result = hot_stocks.hot_stocks_us(
        ["AAPL"],
        yf_module=_EmptyYF,
        sina_provider=provider,
        limit=1,
    )

    assert result[0]["symbol"] == "AAPL"
    assert result[0]["change"] == -1.25
    assert result[0]["source"] == "新浪财经"
