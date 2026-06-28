"""配置模块测试"""
import pytest


class TestDefaultConstants:
    """验证所有默认常量值"""

    def test_macd_fast_default(self):
        import config
        assert config.MACD_FAST == 12

    def test_macd_slow_default(self):
        import config
        assert config.MACD_SLOW == 26

    def test_macd_signal_default(self):
        import config
        assert config.MACD_SIGNAL == 9

    def test_rsi_periods_default(self):
        import config
        assert config.RSI_PERIODS == [6, 12, 24]

    def test_rsi_overbought_default(self):
        import config
        assert config.RSI_OVERBOUGHT == 70

    def test_rsi_oversold_default(self):
        import config
        assert config.RSI_OVERSOLD == 30

    def test_kdj_n_default(self):
        import config
        assert config.KDJ_N == 9

    def test_kdj_overbought_default(self):
        import config
        assert config.KDJ_OVERBOUGHT == 80

    def test_kdj_oversold_default(self):
        import config
        assert config.KDJ_OVERSOLD == 20

    def test_boll_period_default(self):
        import config
        assert config.BOLL_PERIOD == 20

    def test_boll_std_dev_default(self):
        import config
        assert config.BOLL_STD_DEV == 2.0

    def test_ma_periods_default(self):
        import config
        assert config.MA_PERIODS == [5, 10, 20, 60]

    def test_max_retries_default(self):
        import config
        assert config.MAX_RETRIES == 3

    def test_health_fail_threshold_default(self):
        import config
        assert config.HEALTH_FAIL_THRESHOLD == 3

    def test_cache_ttls_positive(self):
        import config
        assert config.CACHE_TTL_REALTIME > 0
        assert config.CACHE_TTL_STOCK_DATA > 0
        assert config.CACHE_TTL_INDICATORS > 0

    def test_daily_report_recommendations_default_disabled(self):
        import config
        assert config.DAILY_REPORT_INCLUDE_RECOMMENDATIONS is False

    def test_t1_plan_auto_default_enabled(self):
        import config
        assert config.T1_PLAN_AUTO_ENABLED is True

    def test_t1_plan_strategies_default_includes_aggressive(self):
        import config
        assert config.T1_PLAN_STRATEGIES == ["短线", "多因子稳健型", "激进突破型"]
        assert config.T1_PLAN_STRATEGY == "短线"
        assert config.T1_PLAN_SECTORS == ["苹果概念", "特斯拉概念"]

    def test_recommend_ranker_default_enabled_without_sorting(self):
        import config
        assert config.RECOMMEND_RANKER_ENABLED is True
        assert config.RECOMMEND_RANKER_SORT is False

    def test_manual_trade_learning_reminder_defaults(self):
        import config
        assert config.MANUAL_TRADE_LEARNING_MIN_CLOSED == 30
        assert config.MANUAL_TRADE_LEARNING_MIN_STRATEGY_CLOSED == 12


class TestEnvVarOverride:
    """验证环境变量覆盖"""

    def test_macd_fast_env_override(self, monkeypatch):
        monkeypatch.setenv("MACD_FAST", "8")
        import importlib, config
        importlib.reload(config)
        assert config.MACD_FAST == 8
        monkeypatch.delenv("MACD_FAST")
        importlib.reload(config)

    def test_macd_slow_env_override(self, monkeypatch):
        monkeypatch.setenv("MACD_SLOW", "20")
        import importlib, config
        importlib.reload(config)
        assert config.MACD_SLOW == 20
        monkeypatch.delenv("MACD_SLOW")
        importlib.reload(config)

    def test_macd_signal_env_override(self, monkeypatch):
        monkeypatch.setenv("MACD_SIGNAL", "7")
        import importlib, config
        importlib.reload(config)
        assert config.MACD_SIGNAL == 7
        monkeypatch.delenv("MACD_SIGNAL")
        importlib.reload(config)

    def test_boll_period_env_override(self, monkeypatch):
        monkeypatch.setenv("BOLL_PERIOD", "14")
        import importlib, config
        importlib.reload(config)
        assert config.BOLL_PERIOD == 14
        monkeypatch.delenv("BOLL_PERIOD")
        importlib.reload(config)

    def test_boll_std_dev_env_override(self, monkeypatch):
        monkeypatch.setenv("BOLL_STD_DEV", "2.5")
        import importlib, config
        importlib.reload(config)
        assert config.BOLL_STD_DEV == 2.5
        monkeypatch.delenv("BOLL_STD_DEV")
        importlib.reload(config)

    def test_max_retries_env_override(self, monkeypatch):
        monkeypatch.setenv("MAX_RETRIES", "5")
        import importlib, config
        importlib.reload(config)
        assert config.MAX_RETRIES == 5
        monkeypatch.delenv("MAX_RETRIES")
        importlib.reload(config)

    def test_ai_model_env_override(self, monkeypatch):
        monkeypatch.setenv("AI_MODEL", "openai/gpt-4")
        import importlib, config
        importlib.reload(config)
        assert config.AI_MODEL == "openai/gpt-4"
        monkeypatch.delenv("AI_MODEL")
        importlib.reload(config)

    def test_ai_enabled_env_override(self, monkeypatch):
        monkeypatch.setenv("AI_ENABLED", "false")
        import importlib, config
        importlib.reload(config)
        assert config.AI_ENABLED is False
        monkeypatch.delenv("AI_ENABLED")
        importlib.reload(config)

    def test_daily_report_recommendations_env_override(self, monkeypatch):
        monkeypatch.setenv("DAILY_REPORT_INCLUDE_RECOMMENDATIONS", "true")
        import importlib, config
        importlib.reload(config)
        assert config.DAILY_REPORT_INCLUDE_RECOMMENDATIONS is True
        monkeypatch.delenv("DAILY_REPORT_INCLUDE_RECOMMENDATIONS")
        importlib.reload(config)

    def test_t1_plan_auto_env_override(self, monkeypatch):
        monkeypatch.setenv("T1_PLAN_AUTO_ENABLED", "false")
        import importlib, config
        importlib.reload(config)
        assert config.T1_PLAN_AUTO_ENABLED is False
        monkeypatch.delenv("T1_PLAN_AUTO_ENABLED")
        importlib.reload(config)

    def test_t1_plan_strategies_env_override(self, monkeypatch):
        monkeypatch.setenv("T1_PLAN_STRATEGIES", "激进突破型, 多因子稳健型")
        import importlib, config
        importlib.reload(config)
        assert config.T1_PLAN_STRATEGIES == ["激进突破型", "多因子稳健型"]
        assert config.T1_PLAN_STRATEGY == "激进突破型"
        monkeypatch.delenv("T1_PLAN_STRATEGIES")
        importlib.reload(config)

    def test_t1_plan_sectors_env_override(self, monkeypatch):
        monkeypatch.setenv("T1_PLAN_SECTORS", "全部, 苹果概念")
        import importlib, config
        importlib.reload(config)
        assert config.T1_PLAN_SECTORS == ["全部", "苹果概念"]
        assert config.T1_PLAN_SECTOR == "全部"
        monkeypatch.delenv("T1_PLAN_SECTORS")
        importlib.reload(config)

    def test_recommend_ranker_env_override(self, monkeypatch):
        monkeypatch.setenv("RECOMMEND_RANKER_ENABLED", "false")
        monkeypatch.setenv("RECOMMEND_RANKER_SORT", "true")
        import importlib, config
        importlib.reload(config)
        assert config.RECOMMEND_RANKER_ENABLED is False
        assert config.RECOMMEND_RANKER_SORT is True
        monkeypatch.delenv("RECOMMEND_RANKER_ENABLED")
        monkeypatch.delenv("RECOMMEND_RANKER_SORT")
        importlib.reload(config)


class TestColorSchemes:
    """验证配色方案完整性"""

    def test_all_three_schemes_exist(self):
        import config
        assert "red_up" in config.COLOR_SCHEMES
        assert "green_up" in config.COLOR_SCHEMES
        assert "colorblind" in config.COLOR_SCHEMES

    def test_scheme_has_required_keys(self):
        import config
        required = ["increasing", "decreasing", "volume_up", "volume_down",
                     "macd_hist_up", "macd_hist_down", "label"]
        for scheme in config.COLOR_SCHEMES.values():
            for key in required:
                assert key in scheme, f"Missing key '{key}' in scheme"

    def test_cn_default_is_red_up(self):
        import config
        assert config.DEFAULT_COLOR_SCHEME["CN"] == "red_up"

    def test_hk_default_is_green_up(self):
        import config
        assert config.DEFAULT_COLOR_SCHEME["HK"] == "green_up"

    def test_us_default_is_green_up(self):
        import config
        assert config.DEFAULT_COLOR_SCHEME["US"] == "green_up"


class TestSignalThresholds:
    """验证信号阈值"""

    def test_buy_threshold_reasonable(self):
        import config
        assert config.SIGNAL_BUY_THRESHOLD > 0

    def test_sell_threshold_reasonable(self):
        import config
        assert config.SIGNAL_SELL_THRESHOLD > 0

    def test_rating_thresholds_count(self):
        import config
        assert len(config.RATING_THRESHOLDS) == 5


class TestAIConfig:
    """验证 AI 配置"""

    def test_ai_api_key_default_none(self):
        import config
        assert config.AI_API_KEY is None

    def test_ai_temperature_reasonable(self):
        import config
        assert 0 <= config.AI_TEMPERATURE <= 1

    def test_ai_cache_ttl_positive(self):
        import config
        assert config.AI_CACHE_TTL_SECONDS > 0
