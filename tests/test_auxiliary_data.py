from unittest.mock import MagicMock

from recommendation_modules import auxiliary_data


def test_fetch_tencent_market_cap_converts_yi_to_yuan():
    parts = [""] * 46
    parts[1] = "测试股 "
    parts[45] = "299.5"
    response = MagicMock(status_code=200, text="~".join(parts))
    requests_module = MagicMock()
    requests_module.get.return_value = response

    market_cap, name, source = auxiliary_data.fetch_tencent_market_cap(
        "300750",
        requests_module=requests_module,
        safe_float=lambda value: float(value),
    )

    assert market_cap == 29_950_000_000
    assert name == "测试股"
    assert source == "腾讯行情"


def test_stock_sector_uses_eastmoney_then_prefix_fallback():
    response = MagicMock(status_code=200)
    response.json.return_value = {"jbzl": {"sshy": ""}}
    requests_module = MagicMock()
    requests_module.get.return_value = response
    cache = {}

    assert auxiliary_data.stock_sector("300750", cache=cache, requests_module=requests_module) == "创业板"
    assert cache["300750"] == "创业板"
