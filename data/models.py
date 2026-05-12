"""数据层标准模型。"""
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class StockProfile:
    """个股基础资料/估值快照的标准返回结构。"""

    symbol: str
    name: str | None = None
    market: str = "CN"
    industry: str | None = None
    listing_date: str | None = None
    latest_price: float | None = None
    total_shares: float | None = None
    float_shares: float | None = None
    market_cap: float | None = None
    float_market_cap: float | None = None
    pe_ttm: float | None = None
    pb: float | None = None
    turnover_rate: float | None = None
    source: str = ""
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转为普通 dict，方便 Streamlit 缓存和 UI 渲染。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StockProfile":
        allowed = {field: data.get(field) for field in cls.__dataclass_fields__}
        return cls(**allowed)


def utc_now_iso() -> str:
    """统一生成数据更新时间。"""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
