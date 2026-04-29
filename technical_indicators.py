"""
技术指标计算模块
包含: RSI、BOLL、KDJ、MACD
"""
import pandas as pd
import numpy as np


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
        计算MACD指标 — 同花顺标准算法
        DIF = EMA(fast) - EMA(slow)
        DEA = EMA(DIF, signal)
        MACD柱 = 2 × (DIF - DEA)
        """
        df = data.copy()

        # 计算快速和慢速EMA
        ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = df['close'].ewm(span=slow, adjust=False).mean()

        # DIF线（同花顺：DIF = EMA(fast) - EMA(slow)）
        df['macd'] = ema_fast - ema_slow

        # DEA线（同花顺：DEA = EMA(DIF, signal)）
        df['macd_signal'] = df['macd'].ewm(span=signal, adjust=False).mean()

        # MACD柱状图（同花顺标准：2倍柱 = 2 × (DIF - DEA)）
        df['macd_hist'] = 2 * (df['macd'] - df['macd_signal'])

        return df

    @staticmethod
    def calculate_rsi(data, periods=[6, 12, 24]):
        """
        计算RSI指标 — 同花顺标准SMA(N,1)算法
        RSI = SMA(涨幅, N, 1) / SMA(|涨跌|, N, 1) × 100
        SMA(N,1) = ewm(alpha=1/N) — 同花顺独有的加权递推平均
        默认计算6日、12日、24日RSI
        """
        df = data.copy()

        for period in periods:
            # 计算价格变化
            delta = df['close'].diff()

            # 分离上涨和下跌
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)

            # 同花顺SMA(N,1): alpha=1/N的指数加权移动平均
            avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

            # 计算RS和RSI
            rs = avg_gain / avg_loss
            rsi_val = 100 - (100 / (1 + rs))
            # 除零保护：avg_gain=0 且 avg_loss=0 时（停牌/一字板）RSI=50
            rsi_val[(avg_gain == 0) & (avg_loss == 0)] = 50
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
        计算布林带 (BOLL) 指标
        中轨 = N日移动平均线
        上轨 = 中轨 + N日标准差 * 倍数
        下轨 = 中轨 - N日标准差 * 倍数
        """
        df = data.copy()

        # 中轨 (简单移动平均线)
        df['boll_mid'] = df['close'].rolling(window=period).mean()

        # 标准差（总体标准差，同花顺标准）
        rolling_std = df['close'].rolling(window=period).std(ddof=0)

        # 上轨和下轨
        df['boll_upper'] = df['boll_mid'] + (rolling_std * std_dev)
        df['boll_lower'] = df['boll_mid'] - (rolling_std * std_dev)

        # 带宽 (衡量波动性)
        df['boll_width'] = (df['boll_upper'] - df['boll_lower']) / df['boll_mid']

        # %B指标 (价格在布林带中的位置)
        df['boll_percent'] = (df['close'] - df['boll_lower']) / (df['boll_upper'] - df['boll_lower'])

        return df

    @staticmethod
    def calculate_kdj(data, n=9, m1=3, m2=3):
        """
        计算KDJ指标 (随机指标) — 同花顺标准算法
        RSV = (当日收盘价 - N日内最低价) / (N日内最高价 - N日内最低价) * 100
        K = SMA(RSV, M1, 1)  — 同花顺中国式SMA递推
        D = SMA(K, M2, 1)
        J = 3K - 2D
        SMA(N,1)首值=第一个RSV，后续SMA_t=[X_t+SMA_{t-1}*(N-1)]/N
        """
        df = data.copy()

        # 检查数据是否足够
        if len(df) < n:
            df['kdj_k'] = 50
            df['kdj_d'] = 50
            df['kdj_j'] = 50
            return df

        # 计算N日内的最高价和最低价
        low_list = df['low'].rolling(window=n, min_periods=n).min()
        high_list = df['high'].rolling(window=n, min_periods=n).max()

        # 计算RSV（处理一字板除零：最高=最低时RSV=50）
        price_range = high_list - low_list
        rsv = (df['close'] - low_list) / price_range.replace(0, np.nan) * 100
        rsv = rsv.fillna(50)

        # 计算平滑系数
        alpha_k = 1 / m1  # K的平滑系数
        alpha_d = 1 / m2  # D的平滑系数

        # 使用标准KDJ递推公式计算
        k_values = []
        d_values = []

        # 同花顺初始值：前n-1天K=D=50，第n天SMA首值=第一个RSV
        for i in range(len(df)):
            if i < n - 1:
                # 前n-1天无有效值
                k_values.append(50)
                d_values.append(50)
            elif i == n - 1:
                # 第n天，SMA(N,1)首值=第一个RSV（同花顺标准做法）
                k = rsv.iloc[i]
                d = rsv.iloc[i]
                k_values.append(k)
                d_values.append(d)
            else:
                # 递推公式
                k = (1 - alpha_k) * k_values[-1] + alpha_k * rsv.iloc[i]
                d = (1 - alpha_d) * d_values[-1] + alpha_d * k
                k_values.append(k)
                d_values.append(d)

        df['kdj_k'] = k_values
        df['kdj_d'] = d_values
        df['kdj_j'] = 3 * df['kdj_k'] - 2 * df['kdj_d']

        return df

    @staticmethod
    def calculate_ma(data, periods=[5, 10, 20, 60]):
        """
        计算移动平均线
        """
        df = data.copy()

        for period in periods:
            df[f'ma{period}'] = df['close'].rolling(window=period).mean()

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
