from tools.build_daily_security_status import build_daily_security_status


class FakeStatusProvider:
    def __init__(self, rows_by_symbol):
        self.rows_by_symbol = rows_by_symbol
        self.queries = []
        self.reconnects = 0

    def query_trade_dates(self, start_date, end_date):
        return ["2026-07-20", "2026-07-21", "2026-07-22"]

    def query_daily_status(self, symbol, start_date, end_date):
        self.queries.append((symbol, start_date, end_date))
        value = self.rows_by_symbol[symbol]
        if isinstance(value, Exception):
            raise value
        return value

    def reconnect(self):
        self.reconnects += 1


def _membership():
    return {
        "000001": [{"listed_date": "1991-04-03", "delisted_date": None}],
        "600001": [{"listed_date": "2026-07-21", "delisted_date": None}],
    }


def test_builder_stores_only_anomalies_and_marks_incomplete_symbols():
    provider = FakeStatusProvider(
        {
            "000001": [
                {"date": "2026-07-20", "trade_status": 1, "is_st": False},
                {"date": "2026-07-21", "trade_status": 1, "is_st": True},
                {"date": "2026-07-22", "trade_status": 0, "is_st": True},
            ],
            "600001": [
                {"date": "2026-07-21", "trade_status": 1, "is_st": False},
            ],
        }
    )
    checkpoints = []

    payload = build_daily_security_status(
        _membership(),
        provider=provider,
        study_start="2026-07-20",
        study_end="2026-07-22",
        checkpoint_every=1,
        checkpoint_callback=checkpoints.append,
    )

    first = payload["symbols"]["000001"]
    second = payload["symbols"]["600001"]
    assert first["complete"] is True
    assert first["st_dates"] == ["2026-07-21", "2026-07-22"]
    assert first["suspended_dates"] == ["2026-07-22"]
    assert "normal_dates" not in first
    assert second["complete"] is False
    assert second["missing_dates_preview"] == ["2026-07-22"]
    assert payload["status"] == "partial"
    assert payload["counts"]["coverage_pct"] == 50.0
    assert len(checkpoints) == 2


def test_builder_resumes_complete_symbols_and_retries_incomplete_ones():
    first_provider = FakeStatusProvider(
        {
            "000001": [
                {"date": "2026-07-20", "trade_status": 1, "is_st": False},
                {"date": "2026-07-21", "trade_status": 1, "is_st": False},
                {"date": "2026-07-22", "trade_status": 1, "is_st": False},
            ],
            "600001": [
                {"date": "2026-07-21", "trade_status": 1, "is_st": False},
            ],
        }
    )
    first_payload = build_daily_security_status(
        _membership(),
        provider=first_provider,
        study_start="2026-07-20",
        study_end="2026-07-22",
    )
    second_provider = FakeStatusProvider(
        {
            "600001": [
                {"date": "2026-07-21", "trade_status": 1, "is_st": False},
                {"date": "2026-07-22", "trade_status": 1, "is_st": False},
            ],
        }
    )

    resumed = build_daily_security_status(
        _membership(),
        provider=second_provider,
        study_start="2026-07-20",
        study_end="2026-07-22",
        existing_payload=first_payload,
    )

    assert second_provider.queries == [
        ("600001", "2026-07-21", "2026-07-22")
    ]
    assert resumed["counts"]["reused_symbols"] == 1
    assert resumed["counts"]["complete_symbols"] == 2
    assert resumed["status"] == "ok"
