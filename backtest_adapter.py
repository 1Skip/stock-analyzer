"""
回测适配层
连接 BacktestEngine 到 stock_analyzer 数据层，JSON 文件存储结果
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from backtest_engine import BacktestEngine, EvaluationConfig, map_signal_to_direction
from config import (
    BACKTEST_EVAL_WINDOW, BACKTEST_MIN_HISTORY, BACKTEST_NEUTRAL_BAND,
    BACKTEST_STOP_LOSS, BACKTEST_TAKE_PROFIT, BACKTEST_RESULTS_DIR,
)

logger = logging.getLogger(__name__)


class BacktestAdapter:
    """回测适配器：逐日滑动窗口计算信号并评估"""

    def __init__(self):
        from data_fetcher import StockDataFetcher
        self.fetcher = StockDataFetcher()

    def run(
        self,
        symbol: str,
        market: str = "CN",
        period: str = "2y",
        eval_window_days: int = BACKTEST_EVAL_WINDOW,
        min_history: int = BACKTEST_MIN_HISTORY,
        neutral_band_pct: float = BACKTEST_NEUTRAL_BAND,
        stop_loss_pct: Optional[float] = BACKTEST_STOP_LOSS,
        take_profit_pct: Optional[float] = BACKTEST_TAKE_PROFIT,
    ) -> dict[str, Any]:
        """对单只股票执行回测

        Args:
            symbol: 股票代码
            market: 市场
            period: 数据周期（建议 2y 以上）
            eval_window_days: 信号后评估天数
            min_history: 计算指标所需最少数据天数
            neutral_band_pct: 中性区间百分比
            stop_loss_pct: 止损百分比（负数，如 -5.0）
            take_profit_pct: 止盈百分比（正数，如 10.0）

        Returns:
            {"results": [...], "summary": {...}}
        """
        logger.info(f"回测开始: {symbol} ({market})")

        # 1. 获取历史数据
        df = self.fetcher.get_stock_data(symbol, period=period, market=market)
        if df is None or df.empty or len(df) < min_history + eval_window_days:
            logger.warning(f"数据不足: {symbol} 只有 {len(df) if df is not None else 0} 条")
            return {"results": [], "summary": {"symbol": symbol, "error": "数据不足"}}

        from technical_indicators import TechnicalIndicators

        # 确保索引是 DatetimeIndex（部分数据源返回字符串索引）
        if not isinstance(df.index, pd.DatetimeIndex):
            logger.warning(f"数据索引非 DatetimeIndex，尝试转换...")
            try:
                df.index = pd.to_datetime(df.index)
            except Exception:
                logger.error(f"无法转换索引为 DatetimeIndex: {type(df.index)}")
                return {"results": [], "summary": {"symbol": symbol, "error": "索引格式错误"}}

        config = EvaluationConfig(
            eval_window_days=eval_window_days,
            neutral_band_pct=neutral_band_pct,
        )

        results = []
        # 2. 逐日滑动窗口
        for i in range(min_history, len(df) - eval_window_days):
            window_data = df.iloc[:i + 1].copy()
            signal_date = window_data.index[-1]

            # 计算指标
            try:
                window_data = TechnicalIndicators.calculate_all(window_data)
                signals = TechnicalIndicators.get_signals(window_data)
                signal = signals.get("recommendation", "观望")
            except Exception:
                continue

            # 忽略观望信号，减少无关回测
            if map_signal_to_direction(signal) == "flat":
                continue

            start_price = float(window_data["close"].iloc[-1])

            # 计算止损/止盈价格
            stop_loss = None
            if stop_loss_pct is not None:
                stop_loss = round(start_price * (1 + stop_loss_pct / 100), 2)
            take_profit = None
            if take_profit_pct is not None:
                take_profit = round(start_price * (1 + take_profit_pct / 100), 2)

            # 前向窗口数据
            forward = df.iloc[i + 1:i + 1 + eval_window_days]
            if len(forward) < eval_window_days:
                continue

            forward_highs = forward["high"].tolist()
            forward_lows = forward["low"].tolist()
            forward_closes = forward["close"].tolist()

            # 转换 forward_dates 为 date 对象
            forward_dates = []
            for d in forward.index:
                if hasattr(d, 'date'):
                    forward_dates.append(d.date())
                elif isinstance(d, datetime):
                    forward_dates.append(d.date())
                else:
                    forward_dates.append(pd.Timestamp(d).date())

            # signal_date 也要作为 date
            if hasattr(signal_date, 'date'):
                ad = signal_date.date()
            elif isinstance(signal_date, datetime):
                ad = signal_date.date()
            else:
                ad = pd.Timestamp(signal_date).date()

            result = BacktestEngine.evaluate_single(
                signal=signal,
                analysis_date=ad,
                start_price=start_price,
                forward_highs=forward_highs,
                forward_lows=forward_lows,
                forward_closes=forward_closes,
                forward_dates=forward_dates,
                stop_loss=stop_loss,
                take_profit=take_profit,
                config=config,
            )
            results.append(result)

        # 3. 汇总
        summary = BacktestEngine.compute_summary(
            results=results,
            symbol=symbol,
            eval_window_days=eval_window_days,
        )
        summary["market"] = market
        summary["period"] = period

        logger.info(f"回测完成: {symbol} — {len(results)} 条, "
                     f"胜率 {summary.get('win_rate_pct')}%, "
                     f"方向准确率 {summary.get('direction_accuracy_pct')}%")

        return {"results": results, "summary": summary}

    def save_results(self, symbol: str, market: str, output: dict[str, Any]) -> str:
        """保存回测结果为 JSON 文件"""
        out_dir = Path(BACKTEST_RESULTS_DIR)
        out_dir.mkdir(exist_ok=True)
        filename = f"{market}_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = out_dir / filename

        def _serialize(obj):
            if hasattr(obj, 'isoformat'):
                return obj.isoformat()
            if isinstance(obj, pd.Timestamp):
                return obj.isoformat()
            raise TypeError(f"不可序列化类型: {type(obj)}")

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2, default=_serialize)

        logger.info(f"回测结果已保存: {filepath}")
        return str(filepath)
