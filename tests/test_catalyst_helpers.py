from datetime import date

from recommendation_modules.catalyst_helpers import recent_items


def test_recent_items_accepts_timezone_aware_dates():
    today = date.today().isoformat()
    items = [
        {"date": f"{today}T08:00:00Z", "title": "UTC"},
        {"date": f"{today}T08:00:00+08:00", "title": "CST"},
    ]

    assert [item["title"] for item in recent_items(items, days=1)] == ["UTC", "CST"]
