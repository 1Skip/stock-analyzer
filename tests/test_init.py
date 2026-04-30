"""冒烟测试：验证所有模块可正常导入"""
import pytest


class TestImports:
    """验证所有核心模块可导入"""

    def test_import_config(self):
        import config
        assert hasattr(config, "MACD_FAST")

    def test_import_technical_indicators(self):
        from technical_indicators import TechnicalIndicators
        assert hasattr(TechnicalIndicators, "calculate_all")

    def test_import_data_fetcher(self):
        from data_fetcher import StockDataFetcher
        assert hasattr(StockDataFetcher, "get_stock_data")

    def test_import_chart_utils(self):
        from chart_utils import MA_CONFIG, resolve_color_scheme
        assert len(MA_CONFIG) == 4

    def test_import_ai_analysis(self):
        from ai_analysis import build_indicator_snapshot, call_ai_analysis
        assert callable(build_indicator_snapshot)

    def test_import_stock_recommendation(self):
        from stock_recommendation import StockRecommender, SECTOR_STOCKS
        assert len(SECTOR_STOCKS) >= 1

    def test_import_watchlist(self):
        import watchlist
        assert hasattr(watchlist, "init_watchlist")

    def test_import_main(self):
        from main import StockAnalyzer
        assert hasattr(StockAnalyzer, "analyze_stock")
