from scripts.check_unsafe_html_usage import scan_unsafe_html


def test_scan_unsafe_html_reports_dynamic_usage(tmp_path):
    path = tmp_path / "page.py"
    path.write_text(
        'st.markdown(f"<b>{name}</b>", unsafe_allow_html=True)\n'
        'st.markdown("<hr>", unsafe_allow_html=True)\n',
        encoding="utf-8",
    )

    rows = scan_unsafe_html([path])

    assert len(rows) == 2
    assert rows[0]["dynamic"] is True
    assert rows[1]["dynamic"] is False
