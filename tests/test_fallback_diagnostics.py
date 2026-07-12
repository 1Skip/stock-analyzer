"""关键行情回退路径的聚合诊断测试。"""
import logging
from types import SimpleNamespace

import data_fetcher
from recommendation_modules import hot_stocks


def _raw_quote(name="测试股", prev_close=10, price=11, volume=1000):
    fields = [name] + ["0"] * 32
    fields[2] = str(prev_close)
    fields[3] = str(price)
    fields[8] = str(volume)
    return ",".join(fields)


class _EmptyBatchProvider:
    def __init__(self, session):
        self.session = session

    def fetch_cn_batch_quotes(self, symbols):
        return {}


def test_batch_quotes_records_fallback_without_changing_result(monkeypatch, caplog):
    calls = {"count": 0}
    response = SimpleNamespace(
        status_code=200,
        text=f'var hq_str_sz000001="{_raw_quote()}";',
    )

    def get_with_first_failure(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("batch endpoint failed")
        return response

    monkeypatch.setattr(data_fetcher, "SinaRealtimeProvider", _EmptyBatchProvider)
    monkeypatch.setattr(data_fetcher._session, "get", get_with_first_failure)
    fetcher = data_fetcher.StockDataFetcher()

    with caplog.at_level(logging.INFO, logger="data_fetcher"):
        result = fetcher.get_batch_realtime_quotes(["000001"], market="CN")

    assert result["000001"]["price"] == 11.0
    assert set(result["000001"]) == {
        "symbol", "name", "price", "open", "high", "low", "volume", "prev_close", "change_pct"
    }
    assert fetcher.last_batch_quote_diagnostics == {
        "status": "fallback",
        "requested": 1,
        "resolved": 1,
        "missing": 0,
        "batch_chunks": 1,
        "batch_failures": 1,
        "batch_empty": 1,
        "single_attempted": 1,
        "single_failures": 0,
        "single_empty": 0,
        "error_types": ["RuntimeError"],
    }
    assert "批量实时行情回退诊断" in caplog.text


def test_batch_quotes_records_unavailable_when_all_requests_fail(monkeypatch, caplog):
    monkeypatch.setattr(data_fetcher, "SinaRealtimeProvider", _EmptyBatchProvider)
    monkeypatch.setattr(
        data_fetcher._session,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("network unavailable")),
    )
    fetcher = data_fetcher.StockDataFetcher()

    with caplog.at_level(logging.INFO, logger="data_fetcher"):
        result = fetcher.get_batch_realtime_quotes(["000001"], market="CN")

    assert result == {}
    diagnostics = fetcher.last_batch_quote_diagnostics
    assert diagnostics["status"] == "unavailable"
    assert diagnostics["batch_failures"] == 1
    assert diagnostics["single_failures"] == 1
    assert diagnostics["resolved"] == 0
    assert diagnostics["missing"] == 1
    assert diagnostics["error_types"] == ["OSError"]
    assert "network unavailable" not in caplog.text


def test_hot_stocks_cn_logs_one_aggregate_diagnostic_and_keeps_partial_result(caplog):
    calls = []
    sz_response = SimpleNamespace(
        status_code=200,
        text=f'var hq_str_sz000001="{_raw_quote()}";',
    )

    class RequestsModule:
        @staticmethod
        def get(url, **kwargs):
            calls.append(url)
            if "sh600000" in url:
                raise RuntimeError("sh endpoint failed")
            return sz_response

    with caplog.at_level(logging.INFO, logger="recommendation_modules.hot_stocks"):
        result = hot_stocks.hot_stocks_cn(
            [{"code": "600000"}, {"code": "000001"}],
            requests_module=RequestsModule,
            limit=2,
        )

    assert [item[hot_stocks.CODE] for item in result] == ["000001"]
    assert "sh600000" in calls[0]
    assert "sz000001" in calls[1]
    messages = [
        record.getMessage()
        for record in caplog.records
        if "A股热门榜批量行情诊断" in record.getMessage()
    ]
    assert len(messages) == 1
    assert "failed_groups=1" in messages[0]
    assert "sh_batch:RuntimeError" in messages[0]
    assert "sh endpoint failed" not in messages[0]
