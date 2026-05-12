"""UI 工具函数测试 — _validate_symbol, _format_val, classify_signal"""
import pytest
import pandas as pd
import numpy as np
from chart_utils import classify_signal
from ui.analyze_page import _validate_symbol, _format_val


class TestClassifySignal:

    def test_buy_signals(self):
        assert classify_signal("MACD 金叉") == "buy"
        assert classify_signal("RSI 超卖") == "buy"
        assert classify_signal("偏多信号") == "buy"
        assert classify_signal("超跌反弹") == "buy"

    def test_sell_signals(self):
        assert classify_signal("MACD 死叉") == "sell"
        assert classify_signal("RSI 超买") == "sell"
        assert classify_signal("偏空信号") == "sell"
        assert classify_signal("技术回调") == "sell"

    def test_neutral_signals(self):
        assert classify_signal("观望") == "neutral"
        assert classify_signal("震荡整理") == "neutral"
        assert classify_signal("") == "neutral"

    def test_non_string_input(self):
        assert classify_signal(123) == "neutral"
        assert classify_signal(None) == "neutral"


class TestValidateSymbol:

    def test_cn_valid(self):
        assert _validate_symbol("000001", "CN") == (True, "")
        assert _validate_symbol("600519", "CN") == (True, "")

    def test_cn_invalid_not_digit(self):
        valid, msg = _validate_symbol("平安银行", "CN")
        assert not valid

    def test_cn_invalid_wrong_length(self):
        valid, msg = _validate_symbol("00001", "CN")
        assert not valid
        valid, msg = _validate_symbol("0000012", "CN")
        assert not valid

    def test_cn_empty(self):
        valid, msg = _validate_symbol("", "CN")
        assert not valid

    def test_us_valid(self):
        assert _validate_symbol("AAPL", "US") == (True, "")
        assert _validate_symbol("BRK.B", "US") == (True, "")

    def test_us_invalid(self):
        valid, msg = _validate_symbol("12345", "US")
        assert not valid

    def test_hk_valid(self):
        assert _validate_symbol("00700", "HK") == (True, "")
        assert _validate_symbol("9988", "HK") == (True, "")

    def test_hk_invalid(self):
        valid, msg = _validate_symbol("007000", "HK")
        assert not valid


class TestFormatVal:

    def test_whole_number(self):
        row = {"close": 123.456}
        assert _format_val(row, "close", 2) == "123.46"

    def test_none_value(self):
        row = {"close": None}
        assert _format_val(row, "close", 2) == "--"

    def test_nan_value(self):
        row = {"close": np.nan}
        assert _format_val(row, "close", 2) == "--"

    def test_missing_key(self):
        row = {}
        assert _format_val(row, "close", 2) == "--"

    def test_precision(self):
        row = {"rsi": 65.4321}
        assert _format_val(row, "rsi", 1) == "65.4"
        assert _format_val(row, "rsi", 3) == "65.432"
