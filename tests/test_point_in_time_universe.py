import pandas as pd

from tools.build_point_in_time_universe import build_membership_rows


def test_membership_builder_combines_current_and_delisted_main_board():
    sh_current = pd.DataFrame([
        {"证券代码": "600000", "公司简称": "浦发银行", "上市日期": "1999-11-10"}
    ])
    sz_current = pd.DataFrame([
        {
            "板块": "主板",
            "A股代码": "000001",
            "A股简称": "平安银行",
            "A股上市日期": "1991-04-03",
            "所属行业": "金融业",
        },
        {
            "板块": "创业板",
            "A股代码": "300001",
            "A股简称": "创业板股",
            "A股上市日期": "2009-10-30",
        },
    ])
    sh_delisted = pd.DataFrame([
        {
            "公司代码": "600001",
            "公司简称": "退市样本",
            "上市日期": "1998-01-22",
            "暂停上市日期": "2009-12-29",
        }
    ])
    sz_delisted = pd.DataFrame([
        {
            "证券代码": "000004",
            "证券简称": "国华退",
            "上市日期": "1990-12-01",
            "终止上市日期": "2026-07-14",
        }
    ])

    rows = build_membership_rows(sh_current, sz_current, sh_delisted, sz_delisted)

    assert [row["symbol"] for row in rows] == ["000001", "000004", "600000", "600001"]
    assert next(row for row in rows if row["symbol"] == "000004")["delisted_date"] == "2026-07-14"
    assert all(row["source"].startswith("AKShare/") for row in rows)
