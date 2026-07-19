from datetime import datetime

import pandas as pd

from data.periods import assess_period_coverage, period_date_range, slice_period


def _frame(rows):
    end = pd.Timestamp.now().normalize()
    if end.weekday() >= 5:
        end -= pd.Timedelta(days=end.weekday() - 4)
    index = pd.date_range(end=end, periods=rows, freq="B")
    return pd.DataFrame({"close": range(rows)}, index=index)


def test_two_and_five_year_ranges_use_real_calendar_boundaries():
    end = datetime(2026, 7, 19)

    assert period_date_range("2y", end) == ("20240719", "20260719")
    assert period_date_range("5y", end) == ("20210719", "20260719")


def test_coverage_rejects_short_history_for_long_period():
    short = _frame(140)
    long = _frame(1310)

    assert assess_period_coverage(short, "5y")["is_complete"] is False
    assert assess_period_coverage(long, "5y")["is_complete"] is True


def test_one_week_slice_does_not_fall_back_to_full_history():
    data = _frame(260)

    result = slice_period(data, "1wk")

    assert 2 <= len(result) <= 7
    assert len(result) < len(data)


def test_cn_fetcher_continues_after_partial_source(monkeypatch):
    from data_fetcher import StockDataFetcher

    partial = _frame(140)
    complete = _frame(520)
    complete.attrs["data_provider"] = "腾讯财经"
    fetcher = StockDataFetcher()
    monkeypatch.setattr(fetcher, "_get_cn_stock_data_mootdx", lambda *args, **kwargs: None)
    monkeypatch.setattr(fetcher, "_get_cn_stock_data_ths", lambda *args, **kwargs: partial.copy())
    monkeypatch.setattr(fetcher, "_get_cn_stock_data_akshare", lambda *args, **kwargs: complete.copy())
    monkeypatch.setattr(fetcher, "_get_cn_stock_data_akshare_em", lambda *args, **kwargs: None)
    monkeypatch.setattr(fetcher, "_get_cn_stock_data_sina_fallback", lambda *args, **kwargs: None)
    monkeypatch.setattr(fetcher, "_get_cn_stock_data_yfinance", lambda *args, **kwargs: None)
    monkeypatch.setattr(fetcher, "_save_offline_cache", lambda *args, **kwargs: None)
    monkeypatch.setattr(fetcher, "_is_cn_daily_kline_fresh", lambda data: True)

    result = fetcher.get_stock_data("000001", period="2y", market="CN", adjust="qfq")

    assert result.attrs["data_source"] == "腾讯财经"
    assert result.attrs["period_coverage"]["is_complete"] is True
    assert len(result) == 520


def test_individual_analysis_fetches_real_five_year_chart_data(monkeypatch):
    import ui.analyze_page as analyze_page

    indicator_data = _frame(260).assign(open=10, high=11, low=9, volume=1000)
    chart_data = _frame(1310).assign(open=10, high=11, low=9, volume=1000)
    calls = []

    def get_data(symbol, period, *args):
        calls.append(period)
        return chart_data.copy() if period == "5y" else indicator_data.copy()

    monkeypatch.setattr(analyze_page, "get_cached_stock_data", get_data)
    monkeypatch.setattr(analyze_page, "get_cached_stock_info", lambda *args: {"shortName": "测试股份"})
    monkeypatch.setattr(analyze_page, "get_cached_realtime_quote", lambda *args: None)
    monkeypatch.setattr(analyze_page, "get_cached_intraday_data", lambda *args: None)
    monkeypatch.setattr(analyze_page, "get_cached_stock_profile", lambda *args: {})
    monkeypatch.setattr(analyze_page, "get_cached_stock_extended_info", lambda *args: {})
    monkeypatch.setattr(analyze_page.TechnicalIndicators, "calculate_all", lambda data: data)
    monkeypatch.setattr(
        analyze_page.TechnicalIndicators,
        "get_signals",
        lambda data: {"recommendation": "观望"},
    )

    result = analyze_page._run_stock_analysis_task("000001", "CN", "5y")

    assert calls.count("1y") == 1
    assert calls.count("5y") == 1
    assert len(result["data"]) == 260
    assert len(result["chart_data"]) == 1310
