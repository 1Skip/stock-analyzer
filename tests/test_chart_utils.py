"""图表工具模块测试"""
import pytest
import pandas as pd
import numpy as np


# ============================================================
# TestMAConfig
# ============================================================

class TestMAConfig:

    def test_four_periods(self):
        from chart_utils import MA_CONFIG
        assert len(MA_CONFIG) == 4

    def test_has_5_10_20_60(self):
        from chart_utils import MA_CONFIG
        for p in [5, 10, 20, 60]:
            assert p in MA_CONFIG

    def test_each_has_required_keys(self):
        from chart_utils import MA_CONFIG
        for period, cfg in MA_CONFIG.items():
            assert 'period' in cfg
            assert 'color' in cfg
            assert 'label' in cfg
            assert cfg['period'] == period

    def test_ma5_is_orange(self):
        from chart_utils import MA_CONFIG
        assert MA_CONFIG[5]['color'] == 'orange'

    def test_ma20_is_blue(self):
        from chart_utils import MA_CONFIG
        assert MA_CONFIG[20]['color'] == 'blue'


# ============================================================
# TestResolveColorScheme
# ============================================================

class TestResolveColorScheme:

    def test_cn_default_is_red_up(self):
        from chart_utils import resolve_color_scheme
        scheme = resolve_color_scheme(market='CN')
        assert scheme['label'] == 'A股传统（红涨绿跌）'

    def test_us_default_is_green_up(self):
        from chart_utils import resolve_color_scheme, COLOR_SCHEMES
        scheme = resolve_color_scheme(market='US')
        assert scheme == COLOR_SCHEMES['green_up']

    def test_hk_default_is_green_up(self):
        from chart_utils import resolve_color_scheme, COLOR_SCHEMES
        scheme = resolve_color_scheme(market='HK')
        assert scheme == COLOR_SCHEMES['green_up']

    def test_explicit_scheme_name(self):
        from chart_utils import resolve_color_scheme
        scheme = resolve_color_scheme(scheme_name='colorblind', market='CN')
        assert '色盲' in scheme['label']

    def test_invalid_scheme_falls_back_to_red_up(self):
        from chart_utils import resolve_color_scheme
        scheme = resolve_color_scheme(scheme_name='nonexistent')
        assert scheme['label'] == 'A股传统（红涨绿跌）'

    def test_unknown_market_defaults_to_red_up(self):
        from chart_utils import resolve_color_scheme
        scheme = resolve_color_scheme(market='JP')
        assert scheme is not None
        assert 'label' in scheme


# ============================================================
# TestGetVolumeColors
# ============================================================

class TestGetVolumeColors:

    def test_up_day_gets_up_color(self):
        from chart_utils import get_volume_colors
        df = pd.DataFrame({
            'open': [10, 10],
            'close': [11, 9],
        })
        colors = get_volume_colors(df, 'red', 'green')
        assert colors[0] == 'red'   # close > open
        assert colors[1] == 'green'  # close < open

    def test_equal_open_close_uses_up_color(self):
        from chart_utils import get_volume_colors
        df = pd.DataFrame({
            'open': [10],
            'close': [10],
        })
        colors = get_volume_colors(df, 'red', 'green')
        assert colors[0] == 'red'  # close >= open

    def test_empty_dataframe(self):
        from chart_utils import get_volume_colors
        df = pd.DataFrame({'open': [], 'close': []})
        colors = get_volume_colors(df, 'red', 'green')
        assert colors == []

    def test_returns_list_of_same_length(self):
        from chart_utils import get_volume_colors
        np.random.seed(0)
        df = pd.DataFrame({
            'open': np.random.randn(100) + 10,
            'close': np.random.randn(100) + 10,
        })
        colors = get_volume_colors(df, 'blue', 'gray')
        assert len(colors) == len(df)


# ============================================================
# TestGetMacdHistColors
# ============================================================

class TestGetMacdHistColors:

    def test_positive_gets_up_color(self):
        from chart_utils import get_macd_hist_colors
        colors = get_macd_hist_colors([0.5, 0.0], 'red', 'green')
        assert colors[0] == 'red'
        assert colors[1] == 'red'  # zero is >= 0

    def test_negative_gets_down_color(self):
        from chart_utils import get_macd_hist_colors
        colors = get_macd_hist_colors([-0.3, -0.01], 'red', 'green')
        assert colors[0] == 'green'
        assert colors[1] == 'green'

    def test_mixed_values(self):
        from chart_utils import get_macd_hist_colors
        colors = get_macd_hist_colors([0.2, -0.5, 0.0, 0.3, -0.1], 'up', 'down')
        assert colors == ['up', 'down', 'up', 'up', 'down']

    def test_empty_list(self):
        from chart_utils import get_macd_hist_colors
        colors = get_macd_hist_colors([], 'up', 'down')
        assert colors == []
