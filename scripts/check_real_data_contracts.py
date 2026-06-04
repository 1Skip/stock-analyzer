"""真实数据契约抽样检查。

默认不访问网络；显式传入 --network 后才调用公开真实数据源。
该脚本只验证字段结构和缺失状态，不生成、不缓存、不补造行情数据。
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class Sample:
    symbol: str
    market: str = "CN"


SAMPLES = [
    Sample("600519"),
    Sample("002609"),
    Sample("300750"),
    Sample("600246"),
    Sample("601012"),
    Sample("000001"),
]

INDEX_SAMPLES = ["000001", "399001", "399006", "899050"]


def _fail(message: str) -> None:
    raise AssertionError(message)


def check_sample(sample: Sample) -> dict:
    from data_fetcher import StockDataFetcher
    from technical_indicators import TechnicalIndicators

    fetcher = StockDataFetcher()
    data = fetcher.get_stock_data(sample.symbol, period="1y", market=sample.market, adjust="qfq")
    if data is None or data.empty:
        _fail(f"{sample.symbol}: 日K为空")
    missing_columns = {"open", "high", "low", "close", "volume"} - set(data.columns)
    if missing_columns:
        _fail(f"{sample.symbol}: 日K缺少字段 {sorted(missing_columns)}")
    if len(data) < 30:
        _fail(f"{sample.symbol}: 日K长度不足 {len(data)}")

    indicators = TechnicalIndicators.calculate_all(data.copy())
    required_indicators = {"ma5", "ma10", "ma20", "ma30", "macd", "kdj_k", "boll_mid"}
    missing_indicators = required_indicators - set(indicators.columns)
    if missing_indicators:
        _fail(f"{sample.symbol}: 指标缺少字段 {sorted(missing_indicators)}")

    quote = fetcher.get_realtime_quote(sample.symbol, market=sample.market)
    quote_status = "available" if quote and quote.get("price") else "missing"
    intraday = fetcher.get_intraday_data(sample.symbol, market=sample.market)
    intraday_status = "available" if intraday is not None and not getattr(intraday, "empty", True) else "missing"
    return {
        "symbol": sample.symbol,
        "market": sample.market,
        "kline_rows": len(data),
        "latest_kline": str(data.index[-1]),
        "quote_status": quote_status,
        "intraday_status": intraday_status,
    }


def check_index(symbol: str) -> dict:
    from data_fetcher import StockDataFetcher

    quote = StockDataFetcher().get_index_realtime(symbol)
    if quote is None:
        _fail(f"{symbol}: 指数行情为空")
    missing = {"symbol", "name", "price", "change_pct", "prev_close"} - set(quote)
    if missing:
        _fail(f"{symbol}: 指数行情缺少字段 {sorted(missing)}")
    return {
        "symbol": symbol,
        "price_status": "available" if quote.get("price") else "missing",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="真实数据契约抽样检查")
    parser.add_argument("--network", action="store_true", help="显式启用真实网络数据源")
    args = parser.parse_args(argv)

    if not args.network:
        print("跳过真实数据契约检查：需要显式传入 --network")
        return 0

    results = [check_sample(sample) for sample in SAMPLES]
    index_results = [check_index(symbol) for symbol in INDEX_SAMPLES]
    for item in results:
        print(
            f"{item['symbol']} {item['market']} rows={item['kline_rows']} "
            f"latest={item['latest_kline']} quote={item['quote_status']} "
            f"intraday={item['intraday_status']}"
        )
    for item in index_results:
        print(f"index {item['symbol']} price={item['price_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
