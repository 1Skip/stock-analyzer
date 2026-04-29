"""
技术指标计算模块
包含: RSI、BOLL、KDJ、MACD
使用 MyTT 库实现，与同花顺/通达信公式精确一致
"""
import pandas as pd
import numpy as np
from MyTT import EMA, MA, KDJ, RSI


class TechnicalIndicators:
    """技术指标计算器"""

    @staticmethod
    def calculate_all(data):
        """
        计算所有技术指标
        返回包含所有指标的DataFrame
        """
        if data is None or data.empty:
            return None

        df = data.copy()

        # 计算各指标
        df = TechnicalIndicators.calculate_macd(df)
        df = TechnicalIndicators.calculate_rsi(df)
        df = TechnicalIndicators.calculate_boll(df)
        df = TechnicalIndicators.calculate_kdj(df)
        df = TechnicalIndicators.calculate_ma(df)

        return df

    @staticmethod
    def calculate_macd(data, fast=12, slow=26, signal=9):
        """
        计算MACD指标 — MyTT底层EMA（跳过RD舍入，与同花顺完全一致）
        DIF = EMA(fast) - EMA(slow)
        DEA = EMA(DIF, signal)
        MACD柱 = 2 × (DIF - DEA)
        """
        df = data.copy()
        close = df['close'].values.astype(np.float64)

        dif = EMA(close, fast) - EMA(close, slow)
        dea = EMA(dif, signal)
        hist = (dif - dea) * 2

        df['macd'] = dif
        df['macd_signal'] = dea
        df['macd_hist'] = hist

        return df

    @staticmethod
    def calculate_rsi(data, periods=[6, 12, 24]):
        """
        计算RSI指标 — MyTT（同花顺标准SMA算法）
        RSI = SMA(涨幅, N, 1) / SMA(|涨跌|, N, 1) × 100
        默认计算6日、12日、24日RSI
        """
        df = data.copy()
        close = df['close'].values.astype(np.float64)

        for period in periods:
            rsi_val = RSI(close, period)
            # MyTT对除零情况返回NaN，填充为50（停牌/一字板）
            rsi_val = np.nan_to_num(rsi_val, nan=50.0)
            df[f'rsi_{period}'] = rsi_val

        # rsi字段用于兼容（指向第一个周期的RSI）
        df['rsi'] = df[f'rsi_{periods[0]}']

        # 添加RSI信号线 (70超买, 30超卖)
        df['rsi_overbought'] = 70
        df['rsi_oversold'] = 30

        return df

    @staticmethod
    def calculate_boll(data, period=20, std_dev=2):
        """
        计算布林带 (BOLL) 指标 — 样本标准差ddof=1（同花顺标准算法）
        中轨 = N日移动平均线
        上轨 = 中轨 + N日样本标准差 × 倍数
        下轨 = 中轨 - N日样本标准差 × 倍数
        """
        df = data.copy()
        close = df['close'].values.astype(np.float64)

        mid = MA(close, period)
        std = pd.Series(close).rolling(period).std(ddof=1).values
        upper = mid + std * std_dev
        lower = mid - std * std_dev

        df['boll_upper'] = upper
        df['boll_mid'] = mid
        df['boll_lower'] = lower

        # 带宽 (衡量波动性)
        df['boll_width'] = (df['boll_upper'] - df['boll_lower']) / df['boll_mid']

        # %B指标 (价格在布林带中的位置)
        df['boll_percent'] = (df['close'] - df['boll_lower']) / (df['boll_upper'] - df['boll_lower'])

        return df

    @staticmethod
    def calculate_kdj(data, n=9, m1=3, m2=3):
        """
        计算KDJ指标 (随机指标) — MyTT（同花顺标准算法）
        RSV = (当日收盘价 - N日内最低价) / (N日内最高价 - N日内最低价) * 100
        K = SMA(RSV, M1, 1)
        D = SMA(K, M2, 1)
        J = 3K - 2D
        """
        df = data.copy()

        if len(df) < n:
            df['kdj_k'] = 50
            df['kdj_d'] = 50
            df['kdj_j'] = 50
            return df

        close = df['close'].values.astype(np.float64)
        high = df['high'].values.astype(np.float64)
        low = df['low'].values.astype(np.float64)

        k, d, j = KDJ(close, high, low, n, m1, m2)

        # MyTT对一字板/停牌除零返回NaN，填充为50
        k = np.nan_to_num(k, nan=50.0)
        d = np.nan_to_num(d, nan=50.0)
        j = np.nan_to_num(j, nan=50.0)

        df['kdj_k'] = k
        df['kdj_d'] = d
        df['kdj_j'] = j

        return df

    @staticmethod
    def calculate_ma(data, periods=[5, 10, 20, 60]):
        """
        计算移动平均线 — MyTT（同花顺标准算法）
        """
        df = data.copy()
        close = df['close'].values.astype(np.float64)

        for period in periods:
            df[f'ma{period}'] = MA(close, period)

        return df

    @staticmethod
    def get_signals(data):
        """
        获取交易信号
        基于多个指标的综合分析
        """
        if data is None or len(data) < 10:
            return {"error": "数据不足"}

        signals = {}
        latest = data.iloc[-1]
        prev = data.iloc[-2] if len(data) > 1 else latest

        # MACD信号
        if latest['macd'] > latest['macd_signal'] and prev['macd'] <= prev['macd_signal']:
            signals['macd'] = "金叉（偏多信号）"
        elif latest['macd'] < latest['macd_signal'] and prev['macd'] >= prev['macd_signal']:
            signals['macd'] = "死叉（偏空信号）"
        elif latest['macd'] > latest['macd_signal']:
            signals['macd'] = "多头趋势"
        else:
            signals['macd'] = "空头趋势"

        # RSI信号
        rsi = latest['rsi']
        if rsi > 70:
            signals['rsi'] = f"超买 ({rsi:.1f})"
        elif rsi < 30:
            signals['rsi'] = f"超卖 ({rsi:.1f})"
        else:
            signals['rsi'] = f"中性 ({rsi:.1f})"

        # KDJ信号
        if latest['kdj_k'] > latest['kdj_d'] and prev['kdj_k'] <= prev['kdj_d']:
            if latest['kdj_k'] < 20:
                signals['kdj'] = "低位金叉（偏多信号，强）"
            else:
                signals['kdj'] = "金叉（偏多信号）"
        elif latest['kdj_k'] < latest['kdj_d'] and prev['kdj_k'] >= prev['kdj_d']:
            if latest['kdj_k'] > 80:
                signals['kdj'] = "高位死叉（偏空信号，强）"
            else:
                signals['kdj'] = "死叉（偏空信号）"
        elif latest['kdj_k'] > 80:
            signals['kdj'] = "K值超买"
        elif latest['kdj_k'] < 20:
            signals['kdj'] = "K值超卖"
        else:
            signals['kdj'] = "中性"

        # 布林带信号
        if latest['close'] > latest['boll_upper']:
            signals['boll'] = "突破上轨，可能回调"
        elif latest['close'] < latest['boll_lower']:
            signals['boll'] = "跌破下轨，可能反弹"
        elif latest['close'] > latest['boll_mid']:
            signals['boll'] = "中轨上方，偏多"
        else:
            signals['boll'] = "中轨下方，偏空"

        # 综合建议（按指标方向计数）
        buy_count = sum([
            "金叉" in signals['macd'],
            "超卖" in signals['rsi'],
            "金叉" in signals['kdj'],
            "反弹" in signals['boll'] or "偏多" in signals['boll']
        ])

        sell_count = sum([
            "死叉" in signals['macd'],
            "超买" in signals['rsi'],
            "死叉" in signals['kdj'],
            "回调" in signals['boll'] or "偏空" in signals['boll']
        ])

        if buy_count >= 3:
            signals['recommendation'] = "偏多信号（强）"
        elif buy_count >= 2:
            signals['recommendation'] = "偏多信号"
        elif sell_count >= 3:
            signals['recommendation'] = "偏空信号（强）"
        elif sell_count >= 2:
            signals['recommendation'] = "偏空信号"
        else:
            signals['recommendation'] = "观望"

        return signals
