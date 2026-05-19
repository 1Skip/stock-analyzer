import json

from data.cache import JsonFileCache


def test_json_file_cache_preserves_distinct_chinese_keys(tmp_path):
    cache = JsonFileCache("recommendation_t1_plans_test", ttl_seconds=3600, cache_dir=tmp_path)

    cache.set("CN:多因子稳健型:全部:5:T1", {"strategy": "多因子稳健型"})
    cache.set("CN:激进突破型:全部:5:T1", {"strategy": "激进突破型"})

    assert cache.get("CN:多因子稳健型:全部:5:T1")["strategy"] == "多因子稳健型"
    assert cache.get("CN:激进突破型:全部:5:T1")["strategy"] == "激进突破型"
    assert cache.get("CN:多因子稳健型:全部:5:T1") != cache.get("CN:激进突破型:全部:5:T1")

    payload = json.loads(cache.path.read_text(encoding="utf-8"))
    assert len(payload) == 2
    assert all(key.startswith("b64_") for key in payload)


def test_json_file_cache_can_read_legacy_collapsed_chinese_key(tmp_path):
    cache = JsonFileCache("recommendation_t1_plans_legacy_test", ttl_seconds=3600, cache_dir=tmp_path)
    cache.path.parent.mkdir(parents=True, exist_ok=True)
    cache.path.write_text(
        '{"CN:_:_:5:T1":{"updated_at":"2099-01-01T00:00:00","value":{"strategy":"短线"}}}',
        encoding="utf-8",
    )

    assert cache.get("CN:短线:算力租赁:5:T1")["strategy"] == "短线"
