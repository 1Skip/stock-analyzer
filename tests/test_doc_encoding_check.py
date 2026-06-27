from scripts.check_doc_encoding import check_paths


def test_check_paths_reports_mojibake_markers(tmp_path):
    path = tmp_path / "bad.md"
    path.write_text("鏂囨。乱码", encoding="utf-8")

    issues = check_paths([path])

    assert issues == [{"path": str(path), "reason": "contains common mojibake markers"}]


def test_check_paths_accepts_clean_ini(tmp_path):
    path = tmp_path / "pytest.ini"
    path.write_text("[pytest]\nmarkers =\n    network: 需要真实网络连接\n", encoding="utf-8")

    assert check_paths([path]) == []
