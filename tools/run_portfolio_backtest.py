"""Run and persist the latest portfolio replay from saved real T+1 plans."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import RUNTIME_CACHE_DIR  # noqa: E402
from data.file_lock import atomic_write_text  # noqa: E402
from strategy_backtest import StrategyBacktestAdapter  # noqa: E402


DEFAULT_OUTPUT = Path(RUNTIME_CACHE_DIR) / "portfolio_backtest_latest.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", default="1y")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--without-benchmark",
        action="store_true",
        help="不获取沪深300；仅用于离线诊断",
    )
    args = parser.parse_args()
    loader = (lambda symbol, period: None) if args.without_benchmark else None
    result = StrategyBacktestAdapter(benchmark_loader=loader).run(period=args.period)
    portfolio = result.get("portfolio") or {}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(args.output, json.dumps(portfolio, ensure_ascii=False, indent=2, default=str))
    print(json.dumps({
        "output": str(args.output),
        "status": portfolio.get("status"),
        "metrics": portfolio.get("metrics"),
        "risk": portfolio.get("risk"),
        "data_quality": portfolio.get("data_quality"),
    }, ensure_ascii=False, default=str))
    return 0 if portfolio.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
