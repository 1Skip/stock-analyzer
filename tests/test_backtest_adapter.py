"""回测适配层测试"""
import json
import pytest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pandas as pd
import numpy as np


# ============================================================
# Helpers
# ============================================================

def _make_ohlc_df(rows=100, start_price=10.0, step=0.1, seed=42):
    """生成带 DatetimeIndex 的模拟 OHLC DataFrame"""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2025-01-02", periods=rows, freq="B")
    closes = start_price + np.cumsum(rng.normal(step / 10, step / 5, rows))
    highs = closes + rng.uniform(0.05, 0.3, rows)
    lows = closes - rng.uniform(0.05, 0.3, rows)
    opens = closes - rng.normal(0, 0.1, rows)
    volume = rng.integers(100000, 10000000, rows)
    return pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": volume,
    }, index=dates)


def _make_adapter():
    from backtest_adapter import BacktestAdapter
    return BacktestAdapter()


# ============================================================
# TestInit
# ============================================================

class TestInit:

    def test_creates_fetcher_instance(self):
        from data_fetcher import StockDataFetcher
        adapter = _make_adapter()
        assert isinstance(adapter.fetcher, StockDataFetcher)


# ============================================================
# TestRun - 数据不足场景
# ============================================================

class TestRunDataInsufficient:

    def test_df_is_none_returns_error(self, monkeypatch):
        adapter = _make_adapter()
        monkeypatch.setattr(adapter.fetcher, "get_stock_data", lambda s, **kw: None)
        output = adapter.run(symbol="000001", market="CN")
        assert output["results"] == []
        assert output["summary"]["error"] == "数据不足"

    def test_df_is_empty_returns_error(self, monkeypatch):
        adapter = _make_adapter()
        monkeypatch.setattr(adapter.fetcher, "get_stock_data",
                           lambda s, **kw: pd.DataFrame())
        output = adapter.run(symbol="000001", market="CN")
        assert output["results"] == []
        assert output["summary"]["error"] == "数据不足"

    def test_df_too_short_returns_error(self, monkeypatch):
        adapter = _make_adapter()
        df = _make_ohlc_df(rows=30)  # < min_history(60) + eval_window(20)
        monkeypatch.setattr(adapter.fetcher, "get_stock_data", lambda s, **kw: df)
        output = adapter.run(symbol="000001", market="CN")
        assert output["results"] == []
        assert output["summary"]["error"] == "数据不足"

    def test_df_exactly_at_threshold_works(self, monkeypatch):
        """刚好 80 条（min_history=60 + eval=20）时应该不会报数据不足"""
        adapter = _make_adapter()
        df = _make_ohlc_df(rows=80)
        monkeypatch.setattr(adapter.fetcher, "get_stock_data", lambda s, **kw: df)
        from technical_indicators import TechnicalIndicators
        monkeypatch.setattr(TechnicalIndicators, "calculate_all", lambda x: x)
        monkeypatch.setattr(TechnicalIndicators, "get_signals",
                           lambda x: {"recommendation": "观望"})
        output = adapter.run(symbol="000001", market="CN", min_history=60, eval_window_days=20)
        # 刚好 80 条时滑动窗口为 range(60, 0) → 空循环，所有信号都是观望 → 0 results
        assert output["summary"].get("error") != "数据不足"


# ============================================================
# TestRun - 索引格式
# ============================================================

class TestRunIndexHandling:

    def test_non_datetime_index_converts_successfully(self, monkeypatch):
        adapter = _make_adapter()
        df = _make_ohlc_df(rows=100)
        df.index = [str(d) for d in df.index]  # 字符串索引
        monkeypatch.setattr(adapter.fetcher, "get_stock_data", lambda s, **kw: df)
        from technical_indicators import TechnicalIndicators
        monkeypatch.setattr(TechnicalIndicators, "calculate_all", lambda x: x)
        monkeypatch.setattr(TechnicalIndicators, "get_signals",
                           lambda x: {"recommendation": "观望"})
        output = adapter.run(symbol="000001", market="CN")
        # 不应返回索引格式错误
        assert output["summary"].get("error") != "索引格式错误"

    def test_non_datetime_index_conversion_fails(self, monkeypatch):
        adapter = _make_adapter()
        df = _make_ohlc_df(rows=100)
        df.index = [object() for _ in range(100)]  # 不可转换的对象
        monkeypatch.setattr(adapter.fetcher, "get_stock_data", lambda s, **kw: df)
        output = adapter.run(symbol="000001", market="CN")
        assert output["results"] == []
        assert output["summary"]["error"] == "索引格式错误"


# ============================================================
# TestRun - 正常流程
# ============================================================

class TestRunNormal:

    def test_produces_results_from_non_flat_signals(self, monkeypatch):
        adapter = _make_adapter()
        df = _make_ohlc_df(rows=100)
        monkeypatch.setattr(adapter.fetcher, "get_stock_data", lambda s, **kw: df)

        from technical_indicators import TechnicalIndicators
        monkeypatch.setattr(TechnicalIndicators, "calculate_all", lambda x: x)
        monkeypatch.setattr(TechnicalIndicators, "get_signals",
                           lambda x: {"recommendation": "偏多信号"})

        output = adapter.run(
            symbol="000001", market="CN",
            min_history=60, eval_window_days=20,
        )
        # 100 - 60 - 20 = 20 iterations, all "偏多信号" → 20 results
        assert len(output["results"]) == 20
        assert output["summary"]["symbol"] == "000001"
        assert output["summary"]["market"] == "CN"
        assert output["summary"]["period"] == "1y"

    def test_flat_signals_are_skipped(self, monkeypatch):
        adapter = _make_adapter()
        df = _make_ohlc_df(rows=100)
        monkeypatch.setattr(adapter.fetcher, "get_stock_data", lambda s, **kw: df)

        from technical_indicators import TechnicalIndicators
        monkeypatch.setattr(TechnicalIndicators, "calculate_all", lambda x: x)
        monkeypatch.setattr(TechnicalIndicators, "get_signals",
                           lambda x: {"recommendation": "观望"})

        output = adapter.run(
            symbol="000001", market="CN",
            min_history=60, eval_window_days=20,
        )
        assert len(output["results"]) == 0

    def test_period_default_is_1y(self, monkeypatch):
        adapter = _make_adapter()
        called_kwargs = {}

        def capture(s, **kw):
            called_kwargs.update(kw)
            return _make_ohlc_df(rows=30)

        monkeypatch.setattr(adapter.fetcher, "get_stock_data", capture)
        adapter.run(symbol="000001", market="CN")
        assert called_kwargs.get("period") == "1y"


# ============================================================
# TestRun - 止损止盈
# ============================================================

class TestRunStopLossTakeProfit:

    def test_stop_loss_none_skips_calculation(self, monkeypatch):
        adapter = _make_adapter()
        df = _make_ohlc_df(rows=100)
        monkeypatch.setattr(adapter.fetcher, "get_stock_data", lambda s, **kw: df)

        from technical_indicators import TechnicalIndicators
        monkeypatch.setattr(TechnicalIndicators, "calculate_all", lambda x: x)
        monkeypatch.setattr(TechnicalIndicators, "get_signals",
                           lambda x: {"recommendation": "偏多信号"})

        output = adapter.run(
            symbol="000001", market="CN",
            min_history=60, eval_window_days=20,
            stop_loss_pct=None, take_profit_pct=None,
        )
        # 未设止损止盈时 hit_stop_loss/hit_take_profit 为 None
        for r in output["results"]:
            assert r.get("hit_stop_loss") is None
            assert r.get("hit_take_profit") is None

    def test_stop_loss_applied_when_set(self, monkeypatch):
        adapter = _make_adapter()
        df = _make_ohlc_df(rows=100)
        monkeypatch.setattr(adapter.fetcher, "get_stock_data", lambda s, **kw: df)

        from technical_indicators import TechnicalIndicators
        monkeypatch.setattr(TechnicalIndicators, "calculate_all", lambda x: x)
        monkeypatch.setattr(TechnicalIndicators, "get_signals",
                           lambda x: {"recommendation": "偏多信号"})

        output = adapter.run(
            symbol="000001", market="CN",
            min_history=60, eval_window_days=20,
            stop_loss_pct=-5.0, take_profit_pct=10.0,
        )
        assert len(output["results"]) > 0


# ============================================================
# TestRun - 基准计算
# ============================================================

class TestRunBenchmark:

    def test_benchmark_shanghai_prefix_uses_000001(self, monkeypatch):
        adapter = _make_adapter()
        df = _make_ohlc_df(rows=100)
        index_calls = []

        def get_stock_data(symbol, **kw):
            index_calls.append(symbol)
            if symbol in ("600519", "000001"):
                return df
            return None

        monkeypatch.setattr(adapter.fetcher, "get_stock_data", get_stock_data)

        from technical_indicators import TechnicalIndicators
        monkeypatch.setattr(TechnicalIndicators, "calculate_all", lambda x: x)
        monkeypatch.setattr(TechnicalIndicators, "get_signals",
                           lambda x: {"recommendation": "偏多信号"})

        adapter.run(symbol="600519", market="CN",
                    min_history=60, eval_window_days=20)
        # 600519 is Shanghai → should use 000001 as benchmark
        assert "000001" in index_calls

    def test_benchmark_shenzhen_uses_399001(self, monkeypatch):
        adapter = _make_adapter()
        df = _make_ohlc_df(rows=100)
        index_calls = []

        def get_stock_data(symbol, **kw):
            index_calls.append(symbol)
            if symbol in ("000001", "399001"):
                return df
            return None

        monkeypatch.setattr(adapter.fetcher, "get_stock_data", get_stock_data)

        from technical_indicators import TechnicalIndicators
        monkeypatch.setattr(TechnicalIndicators, "calculate_all", lambda x: x)
        monkeypatch.setattr(TechnicalIndicators, "get_signals",
                           lambda x: {"recommendation": "偏多信号"})

        adapter.run(symbol="000001", market="CN",
                    min_history=60, eval_window_days=20)
        # 000001 is Shenzhen → should use 399001 as benchmark
        assert "399001" in index_calls

    def test_benchmark_fetch_fails_returns_none(self, monkeypatch):
        adapter = _make_adapter()
        df = _make_ohlc_df(rows=100)

        def get_stock_data(symbol, **kw):
            if symbol == "600519":
                return df
            return None  # benchmark fetch fails

        monkeypatch.setattr(adapter.fetcher, "get_stock_data", get_stock_data)

        from technical_indicators import TechnicalIndicators
        monkeypatch.setattr(TechnicalIndicators, "calculate_all", lambda x: x)
        monkeypatch.setattr(TechnicalIndicators, "get_signals",
                           lambda x: {"recommendation": "偏多信号"})

        output = adapter.run(symbol="600519", market="CN",
                             min_history=60, eval_window_days=20)
        assert output["summary"]["benchmark_return_pct"] is None

    def test_no_benchmark_for_hk_us(self, monkeypatch):
        adapter = _make_adapter()
        df = _make_ohlc_df(rows=100)
        monkeypatch.setattr(adapter.fetcher, "get_stock_data", lambda s, **kw: df)

        from technical_indicators import TechnicalIndicators
        monkeypatch.setattr(TechnicalIndicators, "calculate_all", lambda x: x)
        monkeypatch.setattr(TechnicalIndicators, "get_signals",
                           lambda x: {"recommendation": "偏多信号"})

        output = adapter.run(symbol="00700", market="HK",
                             min_history=60, eval_window_days=20)
        # HK/US 不做基准对比
        assert output["summary"]["benchmark_return_pct"] is None


# ============================================================
# TestRun - 指标计算异常
# ============================================================

class TestRunIndicatorException:

    def test_calculate_all_exception_is_skipped(self, monkeypatch):
        adapter = _make_adapter()
        df = _make_ohlc_df(rows=100)
        monkeypatch.setattr(adapter.fetcher, "get_stock_data", lambda s, **kw: df)

        from technical_indicators import TechnicalIndicators
        monkeypatch.setattr(TechnicalIndicators, "calculate_all",
                           lambda x: (_ for _ in ()).throw(Exception("calc error")))
        monkeypatch.setattr(TechnicalIndicators, "get_signals",
                           lambda x: {"recommendation": "偏多信号"})

        output = adapter.run(symbol="000001", market="CN",
                             min_history=60, eval_window_days=20)
        # 所有迭代都抛异常 → 0 results
        assert len(output["results"]) == 0


# ============================================================
# TestSaveResults
# ============================================================

class TestSaveResults:

    def test_creates_directory_and_writes_file(self, tmp_path, monkeypatch):
        adapter = _make_adapter()
        monkeypatch.setattr("backtest_adapter.BACKTEST_RESULTS_DIR", str(tmp_path / "results"))
        output = {"results": [], "summary": {"symbol": "TEST"}}
        path = adapter.save_results("000001", "CN", output)
        assert Path(path).exists()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["summary"]["symbol"] == "TEST"

    def test_filename_contains_market_symbol(self, tmp_path, monkeypatch):
        adapter = _make_adapter()
        monkeypatch.setattr("backtest_adapter.BACKTEST_RESULTS_DIR", str(tmp_path))
        path = adapter.save_results("000001", "CN", {"results": []})
        filename = Path(path).name
        assert "CN" in filename
        assert "000001" in filename
        assert filename.endswith(".json")

    def test_serialize_isoformat_objects(self, tmp_path, monkeypatch):
        adapter = _make_adapter()
        monkeypatch.setattr("backtest_adapter.BACKTEST_RESULTS_DIR", str(tmp_path))
        output = {"date": date(2025, 6, 1), "dt": datetime(2025, 6, 1, 10, 30)}
        path = adapter.save_results("000001", "CN", output)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert "2025-06-01" in data["date"]
        assert "2025-06-01T10:30:00" in data["dt"]

    def test_serialize_pd_timestamp(self, tmp_path, monkeypatch):
        adapter = _make_adapter()
        monkeypatch.setattr("backtest_adapter.BACKTEST_RESULTS_DIR", str(tmp_path))
        output = {"ts": pd.Timestamp("2025-06-01 10:30")}
        path = adapter.save_results("000001", "CN", output)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert "2025-06-01" in data["ts"]

    def test_unhandled_type_raises_typeerror(self, tmp_path, monkeypatch):
        adapter = _make_adapter()
        monkeypatch.setattr("backtest_adapter.BACKTEST_RESULTS_DIR", str(tmp_path))

        class UnhandledType:
            pass

        with pytest.raises(TypeError, match="不可序列化类型"):
            adapter.save_results("000001", "CN", {"bad": UnhandledType()})

    def test_existing_directory_no_error(self, tmp_path, monkeypatch):
        adapter = _make_adapter()
        out_dir = tmp_path / "results"
        out_dir.mkdir()
        monkeypatch.setattr("backtest_adapter.BACKTEST_RESULTS_DIR", str(out_dir))
        path = adapter.save_results("000001", "CN", {"results": []})
        assert Path(path).exists()
