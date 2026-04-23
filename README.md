# 股票分析系统

一个功能完整的股票分析程序，支持A股、港股和美股，包含K线图、RSI、MACD、KDJ、BOLL等技术指标，以及热门股票和推荐股票功能。

## 功能特点

### 技术指标
- **K线图** - 传统蜡烛图展示价格走势
- **MACD** - 平滑异同移动平均线，判断趋势和买卖时机
- **RSI** - 相对强弱指数，识别超买超卖状态
- **KDJ** - 随机指标，捕捉短期波动
- **BOLL** - 布林带，衡量价格波动和趋势

### 市场支持
- **A股** - 使用akshare获取实时数据
- **港股** - 使用yfinance获取数据
- **美股** - 使用yfinance获取数据

### 特色功能
- **热门股票** - 基于成交量、涨跌幅等指标筛选热门股票
- **推荐股票** - 基于多因子技术分析评分推荐优质股票
- **实时行情** - 获取最新股票价格和交易数据
- **图表展示** - 可视化展示K线和所有技术指标

## 安装步骤

### 1. 安装Python
确保已安装Python 3.8或更高版本

### 2. 安装依赖包
```bash
cd stock_analyzer
pip install -r requirements.txt
```

如果遇到ta-lib安装失败，可以跳过它（程序会使用pandas实现的技术指标）

### 3. 运行程序

#### 交互模式（推荐）
```bash
python main.py -i
```

#### 分析单只股票
```bash
# 分析A股平安银行
python main.py -s 000001 -m CN

# 分析美股苹果
python main.py -s AAPL -m US

# 分析港股腾讯
python main.py -s 0700 -m HK
```

#### 查看热门股票
```bash
python main.py --hot -m CN
```

#### 查看推荐股票
```bash
python main.py --recommend
```

#### 快速演示
```bash
python main.py --demo
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `main.py` | 主程序入口，包含交互式菜单 |
| `data_fetcher.py` | 股票数据获取模块 |
| `technical_indicators.py` | 技术指标计算模块 |
| `chart_plotter.py` | 图表绘制模块 |
| `stock_recommendation.py` | 热门和推荐股票模块 |
| `requirements.txt` | 依赖包列表 |

## 使用示例

### 分析A股
```python
from main import StockAnalyzer

analyzer = StockAnalyzer()

# 分析贵州茅台
analyzer.analyze_stock('600519', market='CN', period='1y')

# 查看热门股票
analyzer.show_hot_stocks(market='CN')

# 获取推荐股票
analyzer.show_recommended_stocks(num_stocks=10)
```

### 分析美股
```python
# 分析特斯拉
analyzer.analyze_stock('TSLA', market='US', period='1y')
```

## 指标说明

### MACD
- **金叉**：MACD线上穿信号线，买入信号
- **死叉**：MACD线下穿信号线，卖出信号
- **柱状图**：MACD与信号线的差值，反映动量

### RSI (14日)
- **>70**：超买区域，可能回调
- **<30**：超卖区域，可能反弹
- **30-70**：正常区间

### KDJ
- **K线**（快线）反映近期价格变动
- **D线**（慢线）反映价格趋势
- **J线** = 3K - 2D，波动最大
- **金叉**：K上穿D，买入信号
- **死叉**：K下穿D，卖出信号

### 布林带
- **上轨**：压力位
- **中轨**：支撑位/压力位
- **下轨**：支撑位
- **带宽扩大**：波动加剧
- **带宽收窄**：可能变盘

## 评分系统

推荐股票的评分基于以下因子：
- MACD趋势 (20分)
- RSI状态 (20分)
- KDJ信号 (20分)
- 布林带位置 (20分)
- 移动平均线趋势 (20分)

总分0-100分：
- **80-100**：强烈买入
- **65-79**：买入
- **50-64**：持有
- **35-49**：减持
- **0-34**：卖出

## 注意事项

1. **数据来源**：A股数据来自东方财富，美股/港股数据来自雅虎财经
2. **网络连接**：程序需要联网获取实时数据
3. **风险提示**：技术分析仅供参考，不构成投资建议
4. **数据延迟**：免费数据可能有15-30分钟延迟

## 常见问题

### Q: 获取数据失败怎么办？
A: 检查网络连接，或稍后再试。部分API有访问频率限制。

### Q: 图表无法显示？
A: 确保已安装matplotlib，或在无GUI环境使用`show_chart=False`参数。

### Q: A股代码格式？
A: 直接使用数字代码，如000001(平安银行)、600519(贵州茅台)、300750(宁德时代)

## 许可证

MIT License
