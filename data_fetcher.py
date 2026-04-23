"""
股票数据获取模块 - 获取真实股票数据
支持A股、港股、美股
针对Streamlit Cloud优化版本（使用yfinance作为主要数据源）
"""
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time


class StockDataFetcher:
    """股票数据获取器"""

    def __init__(self):
        self.cache = {}
        self.use_yfinance_for_cn = True  # 默认使用yfinance获取A股数据（适合境外服务器）

    def get_stock_data(self, symbol, period="1y", interval="1d", market="US"):
        """
        获取股票历史数据
        """
        cache_key = f"{symbol}_{period}_{interval}_{market}"

        if cache_key in self.cache:
            cache_time, cache_data = self.cache[cache_key]
            if datetime.now() - cache_time < timedelta(minutes=5):
                return cache_data

        try:
            if market == "CN":
                # A股优先使用yfinance（在境外服务器更快）
                data = self._get_cn_stock_data_yfinance(symbol, period)
            elif market == "HK":
                ticker = yf.Ticker(f"{symbol}.HK")
                data = ticker.history(period=period, interval=interval)
            else:
                ticker = yf.Ticker(symbol)
                data = ticker.history(period=period, interval=interval)

            if data.empty:
                print(f"未找到股票 {symbol} 的数据")
                return None

            # 标准化列名
            data.columns = [col.lower().replace(' ', '_') for col in data.columns]

            # 缓存数据
            self.cache[cache_key] = (datetime.now(), data)

            return data

        except Exception as e:
            print(f"获取股票数据失败 {symbol}: {str(e)}")
            return None

    def _get_cn_stock_data_yfinance(self, symbol, period):
        """使用yfinance获取A股数据（在境外服务器更快）"""
        # A股代码加后缀
        if '.' not in symbol:
            # 尝试上海交易所
            symbol_yf = f"{symbol}.SS"
            ticker = yf.Ticker(symbol_yf)
            data = ticker.history(period=period)

            if data.empty:
                # 尝试深圳交易所
                symbol_yf = f"{symbol}.SZ"
                ticker = yf.Ticker(symbol_yf)
                data = ticker.history(period=period)
        else:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=period)

        return data

    def get_stock_info(self, symbol, market="US"):
        """获取股票基本信息"""
        try:
            if market == "HK":
                ticker = yf.Ticker(f"{symbol}.HK")
            elif market == "CN":
                # A股使用yfinance
                if '.' not in symbol:
                    # 先尝试上海交易所
                    ticker = yf.Ticker(f"{symbol}.SS")
                    info = ticker.info
                    if info and info.get('shortName'):
                        return info
                    # 再尝试深圳交易所
                    ticker = yf.Ticker(f"{symbol}.SZ")
                else:
                    ticker = yf.Ticker(symbol)
            else:
                ticker = yf.Ticker(symbol)

            info = ticker.info
            return info

        except Exception as e:
            print(f"获取股票信息失败 {symbol}: {str(e)}")
            return {}

    def get_stock_name(self, symbol, market="US"):
        """获取股票名称，优先使用映射表，其次从yfinance获取"""
        # A股优先使用本地映射表（最可靠）
        if market == "CN":
            name = CN_STOCK_NAMES_EXTENDED.get(symbol)
            if name:
                return name

        # 尝试从yfinance获取
        try:
            info = self.get_stock_info(symbol, market)
            if info:
                # 尝试多个可能的字段
                name = info.get('shortName') or info.get('longName')
                if name:
                    return name
        except Exception as e:
            print(f"从yfinance获取名称失败 {symbol}: {e}")

        # 如果都失败了，返回代码本身
        return symbol

    def get_realtime_quote(self, symbol, market="US"):
        """获取实时行情"""
        try:
            if market == "HK":
                ticker = yf.Ticker(f"{symbol}.HK")
            elif market == "CN":
                # A股使用yfinance
                if '.' not in symbol:
                    ticker = yf.Ticker(f"{symbol}.SS")
                else:
                    ticker = yf.Ticker(symbol)
            else:
                ticker = yf.Ticker(symbol)

            hist = ticker.history(period="5d")
            info = ticker.info

            if not hist.empty:
                latest = hist.iloc[-1]
                prev = hist.iloc[-2] if len(hist) > 1 else latest

                return {
                    'symbol': symbol,
                    'name': info.get('shortName', symbol),
                    'price': latest['Close'],
                    'open': latest['Open'],
                    'high': latest['High'],
                    'low': latest['Low'],
                    'volume': latest['Volume'],
                    'prev_close': prev['Close'],
                    'change': ((latest['Close'] - prev['Close']) / prev['Close'] * 100)
                }

        except Exception as e:
            print(f"获取实时行情失败 {symbol}: {str(e)}")

        return None


# 热门股票数据 - 使用静态数据加速（针对Streamlit Cloud优化）
POPULAR_CN_STOCKS = [
    {'code': '000001', 'name': '平安银行'},
    {'code': '000002', 'name': '万科A'},
    {'code': '000858', 'name': '五粮液'},
    {'code': '002594', 'name': '比亚迪'},
    {'code': '300750', 'name': '宁德时代'},
    {'code': '600519', 'name': '贵州茅台'},
    {'code': '601398', 'name': '工商银行'},
    {'code': '601857', 'name': '中国石油'},
    {'code': '601318', 'name': '中国平安'},
    {'code': '601012', 'name': '隆基绿能'},
    {'code': '600036', 'name': '招商银行'},
    {'code': '000333', 'name': '美的集团'},
    {'code': '002415', 'name': '海康威视'},
    {'code': '600276', 'name': '恒瑞医药'},
    {'code': '600887', 'name': '伊利股份'},
    {'code': '601888', 'name': '中国中免'},
    {'code': '002714', 'name': '牧原股份'},
    {'code': '300059', 'name': '东方财富'},
    {'code': '000725', 'name': '京东方A'},
    {'code': '601288', 'name': '农业银行'},
]

# 股票名称映射表（用于快速查找）
CN_STOCK_NAMES = {stock['code']: stock['name'] for stock in POPULAR_CN_STOCKS}

# 扩展更多A股股票名称映射（常用股票）
CN_STOCK_NAMES_EXTENDED = {
    **CN_STOCK_NAMES,
    # 银行金融
    '600036': '招商银行', '601398': '工商银行', '601288': '农业银行', '601939': '建设银行',
    '601988': '中国银行', '601328': '交通银行', '601166': '兴业银行', '600016': '民生银行',
    '601998': '中信银行', '600000': '浦发银行', '600015': '华夏银行', '601818': '光大银行',
    # 保险
    '601318': '中国平安', '601628': '中国人寿', '601601': '中国太保', '601336': '新华保险',
    # 白酒
    '600519': '贵州茅台', '000858': '五粮液', '000568': '泸州老窖', '600809': '山西汾酒',
    '002304': '洋河股份', '000596': '古井贡酒',
    # 新能源
    '300750': '宁德时代', '002594': '比亚迪', '601012': '隆基绿能', '601857': '中国石油',
    '600028': '中国石化', '601088': '中国神华', '600900': '长江电力',
    # 科技
    '002415': '海康威视', '000725': '京东方A', '600276': '恒瑞医药', '600436': '片仔癀',
    '000538': '云南白药', '603288': '海天味业', '000333': '美的集团', '000651': '格力电器',
    '600690': '海尔智家', '601888': '中国中免', '300059': '东方财富', '300033': '同花顺',
    '002714': '牧原股份', '002714': '牧原股份', '600887': '伊利股份', '000001': '平安银行',
    '000002': '万科A', '600030': '中信证券', '601211': '国泰君安', '600837': '海通证券',
    '002230': '科大讯飞', '603259': '药明康德', '300760': '迈瑞医疗', '600031': '三一重工',
    '601668': '中国建筑', '601669': '中国电建', '601390': '中国中铁', '601186': '中国铁建',
    '601766': '中国中车', '600050': '中国联通', '600941': '中国移动', '601728': '中国电信',
    '601229': '上海银行', '600999': '招商证券', '000768': '中航西飞', '600893': '航发动力',
    '000768': '中航西飞', '600372': '中航电子', '600760': '中航沈飞', '601238': '广汽集团',
    '601633': '长城汽车', '600104': '上汽集团', '000625': '长安汽车', '601127': '赛力斯',
    # 半导体/电子
    '603501': '韦尔股份', '603986': '兆易创新', '688981': '中芯国际', '688012': '中微公司',
    '600584': '长电科技', '002049': '紫光国微', '300782': '卓胜微', '603160': '汇顶科技',
    # 医药
    '603392': '万泰生物', '300122': '智飞生物', '300142': '沃森生物', '600196': '复星医药',
    # 其他热门
    '603920': '世运电路', '300999': '金龙鱼', '688111': '金山办公', '603288': '海天味业',
    '300413': '芒果超媒', '002027': '分众传媒', '002352': '顺丰控股', '002120': '韵达股份',
    '601899': '紫金矿业', '601899': '紫金矿业', '002460': '赣锋锂业', '002466': '天齐锂业',
    # 其他股票
    '600480': '凌云股份', '603019': '中科曙光', '600570': '恒生电子', '300033': '同花顺',
    '002230': '科大讯飞', '000063': '中兴通讯', '002236': '大华股份', '002456': '欧菲光',
    '002600': '领益智造', '002475': '立讯精密', '300014': '亿纬锂能', '300124': '汇川技术',
    '300408': '三环集团', '300433': '蓝思科技', '300498': '温氏股份', '300750': '宁德时代',
    '600009': '上海机场', '600048': '保利发展', '600276': '恒瑞医药', '600309': '万华化学',
    '600406': '国电南瑞', '600436': '片仔癀', '600438': '通威股份', '600497': '驰宏锌锗',
    '600570': '恒生电子', '600588': '用友网络', '600660': '福耀玻璃', '600745': '闻泰科技',
    '600809': '山西汾酒', '600845': '宝信软件', '600893': '航发动力', '601012': '隆基绿能',
    '601066': '中信建投', '601088': '中国神华', '601111': '中国国航', '601138': '工业富联',
    '601155': '新城控股', '601318': '中国平安', '601319': '中国人保', '601336': '新华保险',
    '601628': '中国人寿', '601668': '中国建筑', '601669': '中国电建', '601688': '华泰证券',
    '601766': '中国中车', '601788': '光大证券', '601800': '中国交建', '601816': '京沪高铁',
    '601818': '光大银行', '601857': '中国石油', '601888': '中国中免', '601899': '紫金矿业',
    '601933': '永辉超市', '601939': '建设银行', '601958': '金钼股份', '601988': '中国银行',
    '601990': '南京证券', '603000': '人民网', '603019': '中科曙光', '603129': '春风动力',
    '603259': '药明康德', '603288': '海天味业', '603296': '华勤技术', '603501': '韦尔股份',
    '603596': '伯特利', '603658': '安图生物', '603659': '璞泰来', '603799': '华友钴业',
    '603833': '欧派家居', '603986': '兆易创新', '603993': '洛阳钼业',
}

POPULAR_US_STOCKS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX',
    'AMD', 'INTC', 'CRM', 'ADBE', 'PYPL', 'UBER', 'BABA', 'JD',
    'SPY', 'QQQ', 'IWM', 'ARKK'
]
