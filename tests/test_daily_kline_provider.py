from unittest.mock import MagicMock

import pandas as pd

from data.providers.daily_kline_provider import (
    AkshareDailyKlineProvider,
    MootdxDailyKlineProvider,
    SinaDailyKlineProvider,
    ThsDailyKlineProvider,
)


def _rows(count=12):
    dates = pd.date_range("2026-05-01", periods=count, freq="B")
    return [
        {
            "date": date,
            "open": 10 + i,
            "high": 10.5 + i,
            "low": 9.5 + i,
            "close": 10.2 + i,
            "volume": 100000 + i,
        }
        for i, date in enumerate(dates)
    ]


def test_ths_daily_provider_parses_last_js():
    payload_rows = []
    for row in _rows():
        payload_rows.append(
            f"{row['date'].strftime('%Y%m%d')},{row['open']},{row['high']},{row['low']},{row['close']},{row['volume']},1,2"
        )
    session = MagicMock()
    response = MagicMock(status_code=200)
    response.text = 'quotebridge_v6_line_hs_000001_00_last({"data":"' + ";".join(payload_rows) + '"})'
    session.get.return_value = response

    result = ThsDailyKlineProvider(session).fetch("000001", "2y", adjust="qfq")

    assert result is not None
    assert result.attrs["data_provider"] == "同花顺"
    assert result.attrs["adjust_method"] == "前复权"
    assert result.attrs["volume_unit"] == "share"
    assert result["close"].iloc[-1] == 21.2


def test_akshare_daily_provider_normalizes_eastmoney_columns():
    raw = pd.DataFrame(
        {
            "日期": [row["date"] for row in _rows()],
            "开盘": [row["open"] for row in _rows()],
            "收盘": [row["close"] for row in _rows()],
            "最高": [row["high"] for row in _rows()],
            "最低": [row["low"] for row in _rows()],
            "成交量": [row["volume"] for row in _rows()],
        }
    )
    ak = MagicMock()
    ak.stock_zh_a_hist.return_value = raw

    result = AkshareDailyKlineProvider(ak).fetch_eastmoney("000001", "1y", adjust="qfq")

    assert result is not None
    assert result.attrs["data_provider"] == "东方财富"
    assert result.attrs["adjust_method"] == "前复权"
    assert result.attrs["volume_unit"] == "hand"
    assert result["close"].iloc[0] == 10.2


def test_mootdx_daily_provider_normalizes_bars():
    class Client:
        def __init__(self):
            self.closed = False

        def bars(self, symbol, frequency, offset):
            assert symbol == "000001"
            assert frequency == 9
            return pd.DataFrame(
                {
                    "datetime": [row["date"] for row in _rows()],
                    "open": [row["open"] for row in _rows()],
                    "high": [row["high"] for row in _rows()],
                    "low": [row["low"] for row in _rows()],
                    "close": [row["close"] for row in _rows()],
                    "vol": [row["volume"] for row in _rows()],
                }
            )

        def close(self):
            self.closed = True

    client = Client()

    def factory(market="std", timeout=5):
        assert market == "std"
        assert timeout == 5
        return client

    result = MootdxDailyKlineProvider(quotes_factory=factory).fetch("000001", "2y")

    assert result is not None
    assert result.attrs["data_provider"] == "通达信mootdx"
    assert result.attrs["volume_unit"] == "share"
    assert result["close"].iloc[-1] == 21.2
    assert client.closed is True


def test_sina_daily_provider_parses_cn_json():
    session = MagicMock()
    response = MagicMock(status_code=200)
    response.text = str(
        [
            {
                "day": row["date"].strftime("%Y-%m-%d"),
                "open": str(row["open"]),
                "high": str(row["high"]),
                "low": str(row["low"]),
                "close": str(row["close"]),
                "volume": str(row["volume"]),
            }
            for row in _rows()
        ]
    ).replace("'", '"')
    session.get.return_value = response

    result = SinaDailyKlineProvider(session).fetch_cn("000001", "1y")

    assert result is not None
    assert result.attrs["data_provider"] == "新浪财经"
    assert result.attrs["volume_unit"] == "share"
    assert result["open"].iloc[0] == 10
