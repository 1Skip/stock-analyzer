from types import SimpleNamespace

import pytest

from data.providers.baostock_status_provider import (
    BaostockProviderError,
    BaostockStatusProvider,
    to_baostock_code,
)


class FakeResult:
    def __init__(self, fields=None, rows=None, *, error_code="0", error_msg=""):
        self.fields = fields or []
        self.rows = rows or []
        self.error_code = error_code
        self.error_msg = error_msg
        self.index = -1

    def next(self):
        self.index += 1
        return self.index < len(self.rows)

    def get_row_data(self):
        return self.rows[self.index]


class FakeSocket:
    def __init__(self):
        self.timeout = None

    def settimeout(self, value):
        self.timeout = value


class FakeBaostock:
    def __init__(self):
        self.socket = FakeSocket()
        self.common = SimpleNamespace(
            context=SimpleNamespace(default_socket=self.socket)
        )
        self.history_calls = []
        self.logged_out = False

    def login(self):
        return FakeResult()

    def logout(self):
        self.logged_out = True
        return FakeResult()

    def query_trade_dates(self, start_date, end_date):
        return FakeResult(
            ["calendar_date", "is_trading_day"],
            [
                ["2026-07-20", "1"],
                ["2026-07-21", "1"],
                ["2026-07-25", "0"],
            ],
        )

    def query_history_k_data_plus(
        self,
        code,
        fields,
        start_date,
        end_date,
        frequency,
        adjustflag,
    ):
        self.history_calls.append(
            {
                "code": code,
                "fields": fields,
                "start_date": start_date,
                "end_date": end_date,
                "frequency": frequency,
                "adjustflag": adjustflag,
            }
        )
        if fields == "date,tradestatus,isST":
            return FakeResult(
                fields.split(","),
                [
                    ["2026-07-20", "1", "0"],
                    ["2026-07-21", "0", "1"],
                ],
            )
        return FakeResult(
            fields.split(","),
            [
                [
                    "2026-07-20",
                    "10",
                    "10.5",
                    "9.8",
                    "10.2",
                    "1000",
                    "10200",
                    "1.2",
                    "1",
                    "0",
                ],
                [
                    "2026-07-21",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "0",
                    "0",
                ],
            ],
        )


def test_code_mapping_supports_shanghai_and_shenzhen():
    assert to_baostock_code("600000") == "sh.600000"
    assert to_baostock_code("000001") == "sz.000001"
    assert to_baostock_code("sz.300001") == "sz.300001"

    with pytest.raises(ValueError):
        to_baostock_code("430001")


def test_provider_normalizes_trade_calendar_status_and_daily_bars():
    fake = FakeBaostock()

    with BaostockStatusProvider(fake, timeout_seconds=7) as provider:
        trade_dates = provider.query_trade_dates("2026-07-20", "2026-07-25")
        statuses = provider.query_daily_status(
            "600000",
            "2026-07-20",
            "2026-07-21",
        )
        bars = provider.query_daily_bars(
            "000001",
            "2026-07-20",
            "2026-07-21",
        )

    assert trade_dates == ["2026-07-20", "2026-07-21"]
    assert statuses == [
        {"date": "2026-07-20", "trade_status": 1, "is_st": False},
        {"date": "2026-07-21", "trade_status": 0, "is_st": True},
    ]
    assert len(bars) == 1
    assert bars.iloc[0]["close"] == 10.2
    assert bars.iloc[0]["turnover"] == 0.012
    assert bars.attrs["adjust_method"] == "前复权"
    assert fake.history_calls[0]["code"] == "sh.600000"
    assert fake.history_calls[1]["adjustflag"] == "2"
    assert fake.socket.timeout == 7
    assert fake.logged_out is True


def test_provider_raises_explicit_error_instead_of_returning_fake_data():
    fake = FakeBaostock()
    fake.query_trade_dates = lambda **kwargs: FakeResult(
        error_code="10002007",
        error_msg="network error",
    )

    with BaostockStatusProvider(fake) as provider:
        with pytest.raises(BaostockProviderError, match="10002007"):
            provider.query_trade_dates("2026-07-20", "2026-07-21")
