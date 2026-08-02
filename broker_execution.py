"""Safe broker adapter boundary for paper, read-only QMT, and live QMT modes."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib.util
import os
import time
from typing import Any, Protocol

from config import (
    LIVE_TRADING_CONFIRMATION,
    LIVE_TRADING_ENABLED,
    QMT_ACCOUNT_ID,
    QMT_USERDATA_PATH,
    TRADING_MODE,
)


LIVE_CONFIRMATION_PHRASE = "ENABLE_REAL_ORDERS"
SUPPORTED_TRADING_MODES = {"paper", "qmt_read_only", "qmt_live"}


@dataclass(frozen=True)
class BrokerOrderRequest:
    client_order_id: str
    symbol: str
    side: str
    quantity: int
    limit_price: float
    strategy: str = ""
    remark: str = ""


class BrokerAdapter(Protocol):
    def readiness(self) -> dict[str, Any]: ...

    def query_snapshot(self) -> dict[str, Any]: ...

    def submit_order(self, request: BrokerOrderRequest) -> dict[str, Any]: ...

    def cancel_order(self, broker_order_id: str) -> dict[str, Any]: ...


class DisabledBrokerAdapter:
    """Explicit non-live adapter used by default."""

    def readiness(self) -> dict[str, Any]:
        return {
            "mode": "paper",
            "ready": True,
            "read_only": True,
            "live_order_enabled": False,
            "message": "当前为统一模拟账户，不连接券商",
            "checks": {
                "supported_mode": True,
                "windows": os.name == "nt",
                "xtquant_installed": False,
                "userdata_path_configured": False,
                "account_configured": False,
                "live_switch": False,
                "live_confirmation": False,
            },
        }

    def query_snapshot(self) -> dict[str, Any]:
        return {"status": "disabled", "message": "模拟模式没有券商账户快照"}

    def submit_order(self, request: BrokerOrderRequest) -> dict[str, Any]:
        return {
            "status": "blocked",
            "client_order_id": request.client_order_id,
            "message": "模拟模式禁止发送真实委托",
        }

    def cancel_order(self, broker_order_id: str) -> dict[str, Any]:
        return {"status": "blocked", "broker_order_id": broker_order_id, "message": "未连接券商"}


class QmtBrokerAdapter:
    """QMT/MiniQMT adapter with read-only default and triple live-order gate."""

    def __init__(
        self,
        *,
        mode: str = TRADING_MODE,
        userdata_path: str = QMT_USERDATA_PATH,
        account_id: str = QMT_ACCOUNT_ID,
        live_enabled: bool = LIVE_TRADING_ENABLED,
        live_confirmation: str = LIVE_TRADING_CONFIRMATION,
    ):
        self.mode = str(mode or "paper").strip().lower()
        self.userdata_path = str(userdata_path or "").strip()
        self.account_id = str(account_id or "").strip()
        self.live_enabled = bool(live_enabled)
        self.live_confirmation = str(live_confirmation or "")
        self._trader = None
        self._account = None

    def readiness(self) -> dict[str, Any]:
        checks = {
            "supported_mode": self.mode in SUPPORTED_TRADING_MODES,
            "windows": os.name == "nt",
            "xtquant_installed": importlib.util.find_spec("xtquant") is not None,
            "userdata_path_configured": bool(self.userdata_path),
            "account_configured": bool(self.account_id),
            "live_switch": self.live_enabled,
            "live_confirmation": self.live_confirmation == LIVE_CONFIRMATION_PHRASE,
        }
        base_ready = all(
            checks[key]
            for key in (
                "supported_mode",
                "windows",
                "xtquant_installed",
                "userdata_path_configured",
                "account_configured",
            )
        )
        live_order_enabled = bool(
            base_ready
            and self.mode == "qmt_live"
            and checks["live_switch"]
            and checks["live_confirmation"]
        )
        if self.mode == "paper":
            message = "当前为模拟模式，QMT 不连接"
        elif not base_ready:
            message = "QMT 环境未就绪，只能保持禁用"
        elif self.mode == "qmt_read_only":
            message = "QMT 只读查询已具备条件，真实委托被硬阻断"
        elif live_order_enabled:
            message = "QMT 真实委托闸门已全部开启"
        else:
            message = "QMT 可连接，但真实委托闸门未全部开启"
        return {
            "mode": self.mode,
            "ready": base_ready if self.mode != "paper" else True,
            "read_only": not live_order_enabled,
            "live_order_enabled": live_order_enabled,
            "message": message,
            "checks": checks,
        }

    def connect(self) -> dict[str, Any]:
        readiness = self.readiness()
        if self.mode == "paper":
            return {"status": "disabled", "message": readiness["message"]}
        if not readiness["ready"]:
            return {"status": "blocked", "message": readiness["message"], "readiness": readiness}
        try:
            from xtquant.xttrader import XtQuantTrader
            from xtquant.xttype import StockAccount

            session_id = int(time.time() * 1000) % 2_000_000_000
            trader = XtQuantTrader(self.userdata_path, session_id)
            trader.start()
            connection_code = trader.connect()
            if connection_code != 0:
                return {"status": "failed", "message": f"QMT 连接失败，返回码 {connection_code}"}
            account = StockAccount(self.account_id)
            subscribe_code = trader.subscribe(account)
            if subscribe_code != 0:
                return {"status": "failed", "message": f"QMT 账户订阅失败，返回码 {subscribe_code}"}
            self._trader = trader
            self._account = account
            return {"status": "ok", "message": "QMT 已连接并订阅账户"}
        except Exception as exc:
            return {"status": "failed", "message": f"QMT 连接异常: {exc}"}

    def query_snapshot(self) -> dict[str, Any]:
        connected = self._ensure_connected()
        if connected.get("status") != "ok":
            return connected
        try:
            asset = self._trader.query_stock_asset(self._account)
            positions = self._trader.query_stock_positions(self._account) or []
            orders = self._trader.query_stock_orders(self._account) or []
            trades = self._trader.query_stock_trades(self._account) or []
            normalized_orders = []
            for row in orders:
                item = _object_dict(row)
                raw_status = item.get("order_status")
                item["local_status"] = normalize_qmt_order_status(raw_status)
                item["client_order_id"] = item.get("order_remark") or item.get("order_sysid")
                normalized_orders.append(item)
            return {
                "status": "ok",
                "mode": self.mode,
                "asset": _object_dict(asset),
                "positions": [_object_dict(row) for row in positions],
                "orders": normalized_orders,
                "trades": [_object_dict(row) for row in trades],
                "source": "QMT/MiniQMT 本地客户端",
            }
        except Exception as exc:
            return {"status": "failed", "message": f"QMT 查询失败: {exc}"}

    def submit_order(self, request: BrokerOrderRequest) -> dict[str, Any]:
        readiness = self.readiness()
        if not readiness["live_order_enabled"]:
            return {
                "status": "blocked",
                "client_order_id": request.client_order_id,
                "message": "真实委托三重闸门未全部开启",
                "readiness": readiness,
            }
        if request.side not in {"BUY", "SELL"}:
            return {"status": "rejected", "message": "委托方向必须为 BUY 或 SELL"}
        if request.quantity <= 0 or request.quantity % 100:
            return {"status": "rejected", "message": "A股委托数量必须为100股整数手"}
        if request.limit_price <= 0:
            return {"status": "rejected", "message": "限价必须大于0"}
        connected = self._ensure_connected()
        if connected.get("status") != "ok":
            return connected
        try:
            from xtquant import xtconstant

            order_type = xtconstant.STOCK_BUY if request.side == "BUY" else xtconstant.STOCK_SELL
            broker_order_id = self._trader.order_stock(
                self._account,
                _qmt_symbol(request.symbol),
                order_type,
                int(request.quantity),
                xtconstant.FIX_PRICE,
                float(request.limit_price),
                request.strategy[:32],
                (request.remark or request.client_order_id)[:64],
            )
            if int(broker_order_id or -1) < 0:
                return {"status": "failed", "message": f"QMT 委托失败，返回码 {broker_order_id}"}
            return {
                "status": "submitted",
                "client_order_id": request.client_order_id,
                "broker_order_id": str(broker_order_id),
                "request": asdict(request),
            }
        except Exception as exc:
            return {"status": "failed", "message": f"QMT 委托异常: {exc}"}

    def cancel_order(self, broker_order_id: str) -> dict[str, Any]:
        readiness = self.readiness()
        if not readiness["live_order_enabled"]:
            return {
                "status": "blocked",
                "broker_order_id": broker_order_id,
                "message": "真实撤单闸门未全部开启",
            }
        connected = self._ensure_connected()
        if connected.get("status") != "ok":
            return connected
        try:
            result = self._trader.cancel_order_stock(self._account, int(broker_order_id))
            return {
                "status": "submitted" if result == 0 else "failed",
                "broker_order_id": broker_order_id,
                "result_code": result,
            }
        except Exception as exc:
            return {"status": "failed", "message": f"QMT 撤单异常: {exc}"}

    def _ensure_connected(self) -> dict[str, Any]:
        if self._trader is not None and self._account is not None:
            return {"status": "ok"}
        return self.connect()


def build_broker_adapter() -> BrokerAdapter:
    if TRADING_MODE == "paper":
        return DisabledBrokerAdapter()
    return QmtBrokerAdapter()


def _qmt_symbol(symbol: str) -> str:
    value = str(symbol or "").strip().upper()
    if "." in value:
        return value
    return f"{value}.SH" if value.startswith(("5", "6", "9")) else f"{value}.SZ"


def normalize_qmt_order_status(value: Any) -> str:
    """Map QMT order codes to the shared local order-state vocabulary."""
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = None
    mapping = {
        48: "pending",  # 未报
        49: "pending",  # 待报
        50: "pending",  # 已报
        51: "pending",  # 已报待撤
        52: "partially_filled",  # 部成待撤
        53: "partially_filled",  # 部撤
        54: "cancelled",  # 已撤
        55: "partially_filled",  # 部成
        56: "filled",  # 已成
        57: "rejected",  # 废单
        255: "unknown",
    }
    if numeric in mapping:
        return mapping[numeric]
    text = str(value or "").strip().lower()
    text_mapping = {
        "unreported": "pending",
        "wait_reporting": "pending",
        "reported": "pending",
        "part_succeeded": "partially_filled",
        "succeeded": "filled",
        "canceled": "cancelled",
        "cancelled": "cancelled",
        "junk": "rejected",
        "rejected": "rejected",
    }
    return text_mapping.get(text, "unknown")


def _object_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    result = {}
    for name in dir(value):
        if name.startswith("_"):
            continue
        try:
            item = getattr(value, name)
        except Exception:
            continue
        if callable(item):
            continue
        if isinstance(item, (str, int, float, bool, type(None))):
            result[name] = item
    return result
