"""
图表绘制模块
绘制K线图和技术指标
"""
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import pandas as pd

from config import RSI_OVERBOUGHT, RSI_OVERSOLD, KDJ_OVERBOUGHT, KDJ_OVERSOLD
from chart_utils import resolve_color_scheme, get_volume_colors, get_macd_hist_colors, MA_CONFIG

# 设置中文显示
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False


class ChartPlotter:
    """图表绘制器"""

    @staticmethod
    def _draw_candlestick_bars(ax, df, up_color, down_color):
        """在 matplotlib Axes 上绘制K线蜡烛（实体矩形+影线）"""
        for idx, row in df.iterrows():
            if row['close'] >= row['open']:
                color = up_color
                edgecolor = up_color
            else:
                color = down_color
                edgecolor = down_color

            height = abs(row['close'] - row['open'])
            bottom = min(row['close'], row['open'])
            rect = Rectangle((idx - 0.3, bottom), 0.6, height,
                           facecolor=color, edgecolor=edgecolor, linewidth=1)
            ax.add_patch(rect)
            ax.plot([idx, idx], [row['low'], row['high']],
                   color=edgecolor, linewidth=1)

    @staticmethod
    def plot_candlestick(data, title="K线图", save_path=None, show_volume=True, color_scheme='red_up'):
        """
        绘制K线图
        """
        if data is None or data.empty:
            print("无数据可绘制")
            return

        scheme = resolve_color_scheme(color_scheme)
        up_color = scheme['increasing']
        down_color = scheme['decreasing']
        df = data.copy()

        # 创建子图
        if show_volume and 'volume' in df.columns:
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10),
                                            gridspec_kw={'height_ratios': [3, 1]},
                                            sharex=True)
        else:
            fig, ax1 = plt.subplots(1, 1, figsize=(14, 8))
            ax2 = None

        # 绘制K线
        ChartPlotter._draw_candlestick_bars(ax1, df, up_color, down_color)

        # 设置标题和标签
        ax1.set_title(title, fontsize=16, fontweight='bold')
        ax1.set_ylabel('价格', fontsize=12)
        ax1.grid(True, alpha=0.3)

        # 绘制成交量
        if ax2 is not None and 'volume' in df.columns:
            colors = get_volume_colors(df, up_color, down_color)
            ax2.bar(df.index, df['volume'], color=colors, alpha=0.7, width=0.6)
            ax2.set_ylabel('成交量', fontsize=12)
            ax2.set_xlabel('日期', fontsize=12)
            ax2.grid(True, alpha=0.3)

        # 格式化x轴日期
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax1.xaxis.set_major_locator(mdates.AutoDateLocator())

        plt.xticks(rotation=45)
        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"图表已保存到: {save_path}")

        plt.show()

    @staticmethod
    def plot_with_indicators(data, title="股票分析", save_path=None, color_scheme='red_up'):
        """
        绘制K线图和所有技术指标
        使用多子图布局
        """
        if data is None or data.empty:
            print("无数据可绘制")
            return

        scheme = resolve_color_scheme(color_scheme)
        up_color = scheme['increasing']
        down_color = scheme['decreasing']
        df = data.copy()

        # 创建6个子图: K线+MA, 成交量, MACD, RSI, KDJ, BOLL
        fig = plt.figure(figsize=(16, 18))
        gs = fig.add_gridspec(6, 1, height_ratios=[3, 1, 1, 1, 1, 1], hspace=0.05)

        ax1 = fig.add_subplot(gs[0])  # K线+MA
        ax2 = fig.add_subplot(gs[1], sharex=ax1)  # 成交量
        ax3 = fig.add_subplot(gs[2], sharex=ax1)  # MACD
        ax4 = fig.add_subplot(gs[3], sharex=ax1)  # RSI
        ax5 = fig.add_subplot(gs[4], sharex=ax1)  # KDJ
        ax6 = fig.add_subplot(gs[5], sharex=ax1)  # BOLL

        # 1. 绘制K线和移动平均线
        ChartPlotter._draw_candlestick_bars(ax1, df, up_color, down_color)

        # 绘制移动平均线
        for ma_conf in MA_CONFIG.values():
            col_name = f'ma{ma_conf["period"]}'
            if col_name in df.columns:
                ax1.plot(df.index, df[col_name], label=ma_conf['label'],
                        color=ma_conf['color'], linewidth=1)

        ax1.set_title(title, fontsize=16, fontweight='bold')
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)
        ax1.set_ylabel('价格')

        # 2. 成交量
        if 'volume' in df.columns:
            colors = get_volume_colors(df, up_color, down_color)
            ax2.bar(df.index, df['volume'], color=colors, alpha=0.7, width=0.6)
        ax2.set_ylabel('成交量')
        ax2.grid(True, alpha=0.3)

        # 3. MACD
        if 'macd' in df.columns:
            ax3.plot(df.index, df['macd'], label='MACD', color='blue', linewidth=1)
            ax3.plot(df.index, df['macd_signal'], label='Signal', color='red', linewidth=1)

            # MACD柱状图
            macd_hist = df['macd_hist']
            colors = get_macd_hist_colors(macd_hist, up_color, down_color)
            ax3.bar(df.index, macd_hist, color=colors, alpha=0.7, width=0.6)
            ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.5)

        ax3.set_ylabel('MACD')
        ax3.legend(loc='upper left')
        ax3.grid(True, alpha=0.3)

        # 4. RSI
        if 'rsi' in df.columns:
            ax4.plot(df.index, df['rsi'], label='RSI', color='purple', linewidth=1.5)
            ax4.axhline(y=RSI_OVERBOUGHT, color='red', linestyle='--', linewidth=1, label=f'超买({RSI_OVERBOUGHT})')
            ax4.axhline(y=RSI_OVERSOLD, color='green', linestyle='--', linewidth=1, label=f'超卖({RSI_OVERSOLD})')
            ax4.fill_between(df.index, RSI_OVERSOLD, RSI_OVERBOUGHT, alpha=0.1, color='gray')
            ax4.set_ylim(0, 100)

        ax4.set_ylabel('RSI')
        ax4.legend(loc='upper left')
        ax4.grid(True, alpha=0.3)

        # 5. KDJ
        if 'kdj_k' in df.columns:
            ax5.plot(df.index, df['kdj_k'], label='K', color='blue', linewidth=1)
            ax5.plot(df.index, df['kdj_d'], label='D', color='orange', linewidth=1)
            ax5.plot(df.index, df['kdj_j'], label='J', color='purple', linewidth=1)
            ax5.axhline(y=KDJ_OVERBOUGHT, color='red', linestyle='--', linewidth=1)
            ax5.axhline(y=KDJ_OVERSOLD, color='green', linestyle='--', linewidth=1)
            ax5.set_ylabel('KDJ')
            ax5.legend(loc='upper left')
            ax5.grid(True, alpha=0.3)

        # 6. 布林带
        if 'boll_upper' in df.columns:
            ax6.plot(df.index, df['close'], label='价格', color='black', linewidth=1.5)
            ax6.plot(df.index, df['boll_upper'], label='上轨', color='red', linewidth=1)
            ax6.plot(df.index, df['boll_mid'], label='中轨', color='blue', linewidth=1)
            ax6.plot(df.index, df['boll_lower'], label='下轨', color='green', linewidth=1)
            ax6.fill_between(df.index, df['boll_upper'], df['boll_lower'], alpha=0.1, color='blue')

        ax6.set_ylabel('BOLL')
        ax6.set_xlabel('日期')
        ax6.legend(loc='upper left')
        ax6.grid(True, alpha=0.3)

        # 格式化x轴
        ax6.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax6.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.xticks(rotation=45)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"图表已保存到: {save_path}")

        plt.show()

    @staticmethod
    def plot_single_indicator(data, indicator='macd', title=None, save_path=None, color_scheme='red_up'):
        """
        绘制单个指标图
        """
        if data is None or data.empty:
            print("无数据可绘制")
            return

        scheme = resolve_color_scheme(color_scheme)
        up_color = scheme['increasing']
        down_color = scheme['decreasing']
        df = data.copy()
        fig, axes = plt.subplots(2, 1, figsize=(14, 8),
                                gridspec_kw={'height_ratios': [2, 1]},
                                sharex=True)

        ax1, ax2 = axes

        # 上图: K线
        ChartPlotter._draw_candlestick_bars(ax1, df, up_color, down_color)

        ax1.set_title(title or f"{indicator.upper()} 指标分析", fontsize=14, fontweight='bold')
        ax1.grid(True, alpha=0.3)
        ax1.set_ylabel('价格')

        # 下图: 指标
        if indicator == 'macd' and 'macd' in df.columns:
            ax2.plot(df.index, df['macd'], label='MACD', color='blue', linewidth=1.5)
            ax2.plot(df.index, df['macd_signal'], label='Signal', color='red', linewidth=1.5)
            colors = get_macd_hist_colors(df['macd_hist'], up_color, down_color)
            ax2.bar(df.index, df['macd_hist'], color=colors, alpha=0.7, width=0.6)
            ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
            ax2.set_ylabel('MACD')

        elif indicator == 'rsi' and 'rsi' in df.columns:
            ax2.plot(df.index, df['rsi'], label='RSI', color='purple', linewidth=2)
            ax2.axhline(y=RSI_OVERBOUGHT, color='red', linestyle='--', linewidth=1.5, label=f'超买({RSI_OVERBOUGHT})')
            ax2.axhline(y=RSI_OVERSOLD, color='green', linestyle='--', linewidth=1.5, label=f'超卖({RSI_OVERSOLD})')
            ax2.fill_between(df.index, RSI_OVERSOLD, RSI_OVERBOUGHT, alpha=0.1, color='gray')
            ax2.set_ylim(0, 100)
            ax2.set_ylabel('RSI')

        elif indicator == 'kdj' and 'kdj_k' in df.columns:
            ax2.plot(df.index, df['kdj_k'], label='K', color='blue', linewidth=1.5)
            ax2.plot(df.index, df['kdj_d'], label='D', color='orange', linewidth=1.5)
            ax2.plot(df.index, df['kdj_j'], label='J', color='purple', linewidth=1.5)
            ax2.axhline(y=KDJ_OVERBOUGHT, color='red', linestyle='--', linewidth=1)
            ax2.axhline(y=KDJ_OVERSOLD, color='green', linestyle='--', linewidth=1)
            ax2.set_ylabel('KDJ')

        elif indicator == 'boll' and 'boll_upper' in df.columns:
            ax2.plot(df.index, df['close'], label='价格', color='black', linewidth=1.5)
            ax2.plot(df.index, df['boll_upper'], label='上轨', color='red', linewidth=1.5)
            ax2.plot(df.index, df['boll_mid'], label='中轨', color='blue', linewidth=1.5)
            ax2.plot(df.index, df['boll_lower'], label='下轨', color='green', linewidth=1.5)
            ax2.fill_between(df.index, df['boll_upper'], df['boll_lower'], alpha=0.1, color='blue')
            ax2.set_ylabel('BOLL')

        ax2.legend(loc='upper left')
        ax2.grid(True, alpha=0.3)
        ax2.set_xlabel('日期')

        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.xticks(rotation=45)
        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"图表已保存到: {save_path}")

        plt.show()
