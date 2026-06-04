from ui.html_helpers import badge, escape_text, metric_card


def test_escape_text_escapes_dynamic_fields():
    assert escape_text('<script>alert("x")</script>') == '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;'


def test_badge_escapes_label_and_sanitizes_tone():
    html = badge("<b>风险</b>", "warn danger!")

    assert "&lt;b&gt;风险&lt;/b&gt;" in html
    assert "warn danger!" not in html


def test_metric_card_escapes_value_and_note():
    html = metric_card("PE", "<20", "来自 <source>")

    assert "&lt;20" in html
    assert "来自 &lt;source&gt;" in html
