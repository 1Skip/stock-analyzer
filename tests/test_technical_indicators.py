"""
技术指标计算测试
覆盖 MACD / RSI / KDJ / BOLL / MA 及信号生成
"""
import pytest
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from technical_indicators import TechnicalIndicators


class TestMACD:
    """MACD指标测试"""

    def test_macd_columns_exist(self, uptrend_data):
        df = TechnicalIndicators.calculate_macd(uptrend_data)
        assert 'macd' in df.columns
        assert 'macd_signal' in df.columns
        assert 'macd_hist' in df.columns

    def test_macd_no_nan_in_output(self, uptrend_data):
        df = TechnicalIndicators.calculate_macd(uptrend_data)
        assert not df['macd'].isna().all()
        assert not df['macd_signal'].isna().all()

    def test_macd_length_preserved(self, uptrend_data):
        df = TechnicalIndicators.calculate_macd(uptrend_data)
        assert len(df) == len(uptrend_data)

    def test_macd_hist_equals_diff(self, uptrend_data):
        """MACD柱 ≈ 2 × (MACD线 - 信号线)，MyTT内部RD()舍入导致微小差异"""
        df = TechnicalIndicators.calculate_macd(uptrend_data)
        expected = 2 * (df['macd'] - df['macd_signal'])
        diff = (df['macd_hist'] - expected).abs()
        # MyTT逐步骤RD()舍入，与直接计算差≤0.003
        assert (diff.dropna() <= 0.003).all()

    def test_macd_uptrend_positive(self, uptrend_data):
        """上涨趋势中MACD应在后期转为正值"""
        df = TechnicalIndicators.calculate_macd(uptrend_data)
        last_half = df['macd'].iloc[-15:]
        assert last_half.mean() > 0

    def test_macd_downtrend_negative(self, downtrend_data):
        """下跌趋势中MACD应在后期转为负值"""
        df = TechnicalIndicators.calculate_macd(downtrend_data)
        last_half = df['macd'].iloc[-15:]
        assert last_half.mean() < 0

    def test_macd_custom_params(self, uptrend_data):
        """自定义参数"""
        df = TechnicalIndicators.calculate_macd(uptrend_data, fast=6, slow=19, signal=6)
        assert 'macd' in df.columns


class TestRSI:
    """RSI指标测试"""

    def test_rsi_columns_exist(self, uptrend_data):
        df = TechnicalIndicators.calculate_rsi(uptrend_data)
        assert 'rsi_6' in df.columns
        assert 'rsi_12' in df.columns
        assert 'rsi_24' in df.columns
        assert 'rsi' in df.columns

    def test_rsi_range(self, uptrend_data):
        """RSI值应在0-100之间"""
        df = TechnicalIndicators.calculate_rsi(uptrend_data)
        valid = df['rsi_6'].dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_rsi_default_is_rsi6(self, uptrend_data):
        df = TechnicalIndicators.calculate_rsi(uptrend_data)
        pd.testing.assert_series_equal(
            df['rsi'].round(6), df['rsi_6'].round(6), check_names=False
        )

    def test_rsi_uptrend_high(self, uptrend_data):
        """持续上涨RSI应偏高"""
        df = TechnicalIndicators.calculate_rsi(uptrend_data)
        last_rsi = df['rsi_6'].iloc[-1]
        assert last_rsi > 50

    def test_rsi_downtrend_low(self, downtrend_data):
        """持续下跌RSI应偏低"""
        df = TechnicalIndicators.calculate_rsi(downtrend_data)
        last_rsi = df['rsi_6'].iloc[-1]
        assert last_rsi < 50

    def test_rsi_flat_price_is_50(self, flat_price_data):
        """一字横盘RSI=50（除零保护）"""
        df = TechnicalIndicators.calculate_rsi(flat_price_data)
        valid = df['rsi_6'].dropna()
        assert len(valid) > 0
        assert all(abs(v - 50) < 1 for v in valid)

    def test_rsi_periods_list(self, uptrend_data):
        """自定义周期列表"""
        df = TechnicalIndicators.calculate_rsi(uptrend_data, periods=[7, 14])
        assert 'rsi_7' in df.columns
        assert 'rsi_14' in df.columns
        assert 'rsi' in df.columns


class TestKDJ:
    """KDJ指标测试"""

    def test_kdj_columns_exist(self, uptrend_data):
        df = TechnicalIndicators.calculate_kdj(uptrend_data)
        assert 'kdj_k' in df.columns
        assert 'kdj_d' in df.columns
        assert 'kdj_j' in df.columns

    def test_kdj_j_formula(self, uptrend_data):
        """J = 3K - 2D"""
        df = TechnicalIndicators.calculate_kdj(uptrend_data)
        expected_j = 3 * df['kdj_k'] - 2 * df['kdj_d']
        pd.testing.assert_series_equal(
            df['kdj_j'].round(6), expected_j.round(6), check_names=False
        )

    def test_kdj_range_typical(self, uptrend_data):
        """KDJ值应在0-100附近（J可能超出）"""
        df = TechnicalIndicators.calculate_kdj(uptrend_data)
        valid_k = df['kdj_k'].dropna()
        valid_d = df['kdj_d'].dropna()
        assert (valid_k >= 0).all() and (valid_k <= 100).all()
        assert (valid_d >= 0).all() and (valid_d <= 100).all()

    def test_kdj_flat_price_is_50(self, flat_price_data):
        """一字横盘KDJ应稳定在50附近"""
        df = TechnicalIndicators.calculate_kdj(flat_price_data)
        valid = df['kdj_k'].dropna()
        assert len(valid) > 0
        assert all(abs(v - 50) < 1 for v in valid)

    def test_kdj_short_data(self, short_data):
        """数据不足时仍应返回有效值"""
        df = TechnicalIndicators.calculate_kdj(short_data)
        assert 'kdj_k' in df.columns
        assert not df['kdj_k'].isna().all()

    def test_kdj_uptrend_high(self, uptrend_data):
        """持续上涨KDJ应偏高"""
        df = TechnicalIndicators.calculate_kdj(uptrend_data)
        assert df['kdj_k'].iloc[-1] > 50


class TestBOLL:
    """布林带测试"""

    def test_boll_columns_exist(self, uptrend_data):
        df = TechnicalIndicators.calculate_boll(uptrend_data)
        assert 'boll_upper' in df.columns
        assert 'boll_mid' in df.columns
        assert 'boll_lower' in df.columns
        assert 'boll_width' in df.columns
        assert 'boll_percent' in df.columns

    def test_boll_order(self, uptrend_data):
        """上轨 >= 中轨 >= 下轨"""
        df = TechnicalIndicators.calculate_boll(uptrend_data)
        valid = df.dropna(subset=['boll_upper', 'boll_mid', 'boll_lower'])
        assert (valid['boll_upper'] >= valid['boll_mid']).all()
        assert (valid['boll_mid'] >= valid['boll_lower']).all()

    def test_boll_percent_range(self, uptrend_data):
        """%B在0-1附近（价格在带宽内波动）"""
        df = TechnicalIndicators.calculate_boll(uptrend_data)
        valid = df['boll_percent'].dropna()
        assert valid.between(-0.5, 1.5).all()

    def test_boll_width_positive(self, uptrend_data):
        """带宽为正"""
        df = TechnicalIndicators.calculate_boll(uptrend_data)
        valid = df['boll_width'].dropna()
        assert (valid > 0).all()


class TestMA:
    """移动平均线测试"""

    def test_ma_columns_exist(self, uptrend_data):
        df = TechnicalIndicators.calculate_ma(uptrend_data)
        assert 'ma5' in df.columns
        assert 'ma10' in df.columns
        assert 'ma20' in df.columns
        assert 'ma60' in df.columns

    def test_ma_uptrend_order(self, uptrend_data):
        """上涨趋势：短均线 > 长均线"""
        df = TechnicalIndicators.calculate_ma(uptrend_data)
        last = df.iloc[-1]
        assert last['ma5'] > last['ma20']

    def test_ma_downtrend_order(self, downtrend_data):
        """下跌趋势：短均线 < 长均线"""
        df = TechnicalIndicators.calculate_ma(downtrend_data)
        last = df.iloc[-1]
        assert last['ma5'] < last['ma20']


class TestCalculateAll:
    """综合计算测试"""

    def test_all_columns_exist(self, uptrend_data):
        df = TechnicalIndicators.calculate_all(uptrend_data)
        expected = ['macd', 'macd_signal', 'macd_hist',
                    'rsi', 'rsi_6', 'rsi_12', 'rsi_24',
                    'kdj_k', 'kdj_d', 'kdj_j',
                    'boll_upper', 'boll_mid', 'boll_lower',
                    'ma5', 'ma10', 'ma20', 'ma60']
        for col in expected:
            assert col in df.columns, f"缺少列: {col}"

    def test_none_input(self):
        df = TechnicalIndicators.calculate_all(None)
        assert df is None

    def test_empty_input(self):
        df = TechnicalIndicators.calculate_all(pd.DataFrame())
        assert df is None


class TestSignals:
    """交易信号测试"""

    def test_signals_structure(self, uptrend_data):
        df = TechnicalIndicators.calculate_all(uptrend_data)
        signals = TechnicalIndicators.get_signals(df)
        for key in ['macd', 'rsi', 'kdj', 'boll', 'recommendation']:
            assert key in signals

    def test_signals_no_error(self, uptrend_data):
        df = TechnicalIndicators.calculate_all(uptrend_data)
        signals = TechnicalIndicators.get_signals(df)
        assert 'error' not in signals

    def test_signals_short_data(self, short_data):
        df = TechnicalIndicators.calculate_all(short_data)
        signals = TechnicalIndicators.get_signals(df)
        # 数据不足返回error
        if len(short_data) < 10:
            assert 'error' in signals

    def test_signals_directional_language(self, uptrend_data):
        """验证信号使用偏向性语言而非绝对语言"""
        df = TechnicalIndicators.calculate_all(uptrend_data)
        signals = TechnicalIndicators.get_signals(df)
        # 不应包含旧的绝对语言
        assert '强烈买入' not in str(signals)
        assert '强烈卖出' not in str(signals)

    def test_signals_uptrend_bullish(self, uptrend_data):
        """上涨趋势应偏多"""
        df = TechnicalIndicators.calculate_all(uptrend_data)
        signals = TechnicalIndicators.get_signals(df)
        assert '偏多' in signals['recommendation'] or '观望' in signals['recommendation']

    def test_signals_downtrend_bearish(self, downtrend_data):
        """下跌趋势应偏空"""
        df = TechnicalIndicators.calculate_all(downtrend_data)
        signals = TechnicalIndicators.get_signals(df)
        assert '偏空' in signals['recommendation'] or '观望' in signals['recommendation']

    def test_signals_empty_data(self):
        signals = TechnicalIndicators.get_signals(None)
        assert 'error' in signals
