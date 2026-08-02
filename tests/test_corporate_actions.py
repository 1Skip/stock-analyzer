import pandas as pd
import pytest

from data.providers.corporate_action_provider import AkShareCorporateActionProvider
from data.services.corporate_action_service import CorporateActionService
from paper_trading import PaperTradingService


class _StaticCorporateActionService:
    def __init__(self, events, *, status="ok", errors=None):
        self.events = list(events)
        self.status = status
        self.errors = list(errors or [])

    def get_due_events(self, symbol, *, as_of_date, held_since=None):
        due = []
        for event in self.events:
            if event.get("symbol") != symbol:
                continue
            effective_date = str(event.get("effective_date") or "")
            eligibility_date = str(event.get("record_date") or effective_date)
            if effective_date <= as_of_date and (not held_since or eligibility_date >= held_since):
                due.append(dict(event))
        return {
            "status": self.status,
            "source": "测试真实接口夹具",
            "cache_hit": False,
            "events": due,
            "due_event_count": len(due),
            "errors": self.errors,
        }


class _Provider:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def get_events(self, symbol, *, timeout_seconds):
        self.calls += 1
        return {**self.result, "symbol": symbol}


def _seed_position(service, *, symbol="000001", buy_date="2026-06-10"):
    account = service.get_account()
    account["positions"][symbol] = {
        "symbol": symbol,
        "name": "平安银行",
        "industry": "银行",
        "strategy": "实验策略",
        "strategy_version": "test",
        "strategy_rule_id": "test_rule",
        "quantity": 1000,
        "available_quantity": 1000,
        "average_price": 10.0,
        "buy_fee": 5.0,
        "buy_date": buy_date,
        "max_holding_days": 30,
        "price_source": "测试真实接口夹具",
    }
    service._save(account)


def test_cninfo_dividend_normalization_splits_cash_and_share_components():
    frame = pd.DataFrame([{
        "实施方案公告日期": "2026-06-05",
        "分红类型": "年度分红",
        "送股比例": 1.0,
        "转增比例": 2.0,
        "派息比例": 3.6,
        "股权登记日": "2026-06-11",
        "除权日": "2026-06-12",
        "派息日": "2026-06-12",
        "股份到账日": "2026-06-12",
        "实施方案分红说明": "10送1转2派3.6元",
        "报告时间": "2025年报",
    }])

    events = AkShareCorporateActionProvider.normalize_dividend_events("000001", frame)

    assert [event["action_type"] for event in events] == [
        "cash_dividend",
        "share_distribution",
    ]
    assert events[0]["cash_per_share"] == pytest.approx(0.36)
    assert events[1]["additional_shares_per_share"] == pytest.approx(0.3)
    assert events[0]["action_id"] != events[1]["action_id"]
    assert events[0]["data_status"] == "verified"


def test_cninfo_rights_issue_normalization_keeps_manual_subscription_fields():
    frame = pd.DataFrame([{
        "记录标识": 26002457,
        "公告日期": "2000-10-21",
        "配股比例": 3.0,
        "配股价格": 8.0,
        "股权登记日": "2000-11-03",
        "除权基准日": "2000-11-06",
        "配股缴款起始日": "2000-11-07",
        "配股缴款截止日": "2000-11-20",
        "配股上市日": "2000-12-08",
    }])

    events = AkShareCorporateActionProvider.normalize_rights_issue_events("000001", frame)

    assert len(events) == 1
    assert events[0]["action_type"] == "rights_issue"
    assert events[0]["rights_per_share"] == pytest.approx(0.3)
    assert events[0]["rights_price"] == 8.0
    assert events[0]["effective_date"] == "2000-11-03"


def test_corporate_action_service_caches_only_complete_real_result(tmp_path):
    provider = _Provider({
        "status": "ok",
        "source": "测试真实接口夹具",
        "events": [],
        "event_count": 0,
        "errors": [],
    })
    service = CorporateActionService(provider=provider, cache_dir=tmp_path)

    first = service.get_events("000001")
    second = service.get_events("000001")

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert provider.calls == 1


def test_paper_reconciliation_applies_actions_once_and_never_auto_subscribes_rights(tmp_path):
    events = [
        {
            "action_id": "cash-20260612",
            "symbol": "000001",
            "action_type": "cash_dividend",
            "effective_date": "2026-06-12",
            "record_date": "2026-06-11",
            "ex_date": "2026-06-12",
            "cash_per_share": 0.36,
            "cash_per_10_shares": 3.6,
            "source": "巨潮资讯历史分红/AKShare",
            "data_status": "verified",
        },
        {
            "action_id": "shares-20260612",
            "symbol": "000001",
            "action_type": "share_distribution",
            "effective_date": "2026-06-12",
            "record_date": "2026-06-11",
            "ex_date": "2026-06-12",
            "additional_shares_per_share": 0.2,
            "source": "巨潮资讯历史分红/AKShare",
            "data_status": "verified",
        },
        {
            "action_id": "rights-20260611",
            "symbol": "000001",
            "action_type": "rights_issue",
            "effective_date": "2026-06-11",
            "record_date": "2026-06-11",
            "rights_per_share": 0.3,
            "rights_price": 8.0,
            "source": "巨潮资讯配股实施方案/AKShare",
            "data_status": "verified",
        },
    ]
    service = PaperTradingService(
        cache_dir=tmp_path,
        corporate_action_service=_StaticCorporateActionService(events),
        strategy_rotation_enabled=False,
    )
    _seed_position(service)

    first = service.reconcile(as_of_date="2026-06-12")
    second = service.reconcile(as_of_date="2026-06-12")

    first_position = first["summary"]["positions"][0]
    assert first["corporate_actions"]["applied"] == 2
    assert first["corporate_actions"]["rights_not_subscribed"] == 1
    assert first["summary"]["cash"] == pytest.approx(1_000_360.0)
    assert first_position["quantity"] == 1200
    assert first_position["available_quantity"] == 1200
    assert first_position["average_price"] == pytest.approx(10000 / 1200, abs=0.0001)
    assert second["corporate_actions"]["duplicates"] == 3
    assert second["summary"]["cash"] == pytest.approx(first["summary"]["cash"])
    assert len(second["summary"]["corporate_actions"]) == 3
    assert any(
        action["status"] == "not_subscribed"
        for action in second["summary"]["corporate_actions"]
    )
    assert second["summary"]["audit"]["valid"] is True
    assert len([
        alert for alert in second["summary"]["open_alerts"]
        if str(alert.get("code") or "").startswith("RIGHTS_ISSUE_NOT_SUBSCRIBED:")
    ]) == 1


def test_paper_reconciliation_skips_event_when_position_was_bought_after_record_date(tmp_path):
    event = {
        "action_id": "cash-old",
        "symbol": "000001",
        "action_type": "cash_dividend",
        "effective_date": "2026-06-12",
        "record_date": "2026-06-11",
        "cash_per_share": 0.36,
        "source": "巨潮资讯历史分红/AKShare",
        "data_status": "verified",
    }
    service = PaperTradingService(
        cache_dir=tmp_path,
        corporate_action_service=_StaticCorporateActionService([event]),
        strategy_rotation_enabled=False,
    )
    _seed_position(service, buy_date="2026-06-12")

    result = service.reconcile(as_of_date="2026-06-12")

    assert result["corporate_actions"]["events_due"] == 0
    assert result["summary"]["cash"] == 1_000_000
    assert result["summary"]["corporate_actions"] == []
