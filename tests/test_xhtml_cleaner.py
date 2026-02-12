from __future__ import annotations

from lxml import html as lxml_html

from wordlift_sdk.render.cleanup_options import CleanupOptions
from wordlift_sdk.render.xhtml_cleaner import XhtmlCleaner


def test_compact_text_variants():
    cleaner = XhtmlCleaner()

    assert cleaner._compact_text(None, 10) is None
    assert cleaner._compact_text("   ", 10) is None
    assert cleaner._compact_text("a   b   c", 10) == "a b c"
    assert cleaner._compact_text("abcdef", 3) == "abc"
    assert cleaner._compact_text("abcdef", 5) == "ab..."


def test_strip_unwanted_tags_and_compact_nodes():
    cleaner = XhtmlCleaner()
    doc = lxml_html.document_fromstring(
        "<html><body><script>x</script><p>  too   much   space </p></body></html>"
    )

    cleaner._strip_unwanted_tags(doc, ("script",))
    assert not doc.xpath("//script")

    cleaner._compact_text_nodes(doc, 8)
    p_text = doc.xpath("string(//p)")
    assert p_text.startswith("too")


def test_cap_text_content_and_clear_tail_after_limit():
    cleaner = XhtmlCleaner()
    doc = lxml_html.document_fromstring(
        "<html><body><p>abcdefghij</p><p>second</p></body></html>"
    )

    cleaner._cap_text_content(doc, 5)

    first = doc.xpath("//p")[0]
    second = doc.xpath("//p")[1]
    assert first.text == "abcde"
    assert second.text is None


def test_trim_elements_to_size_and_clean_end_to_end():
    cleaner = XhtmlCleaner()
    xhtml = (
        "<html><body>"
        + "".join(f"<div>{i}</div>" for i in range(100))
        + "</body></html>"
    )

    options = CleanupOptions(
        remove_tags=("script", "style"),
        max_xhtml_chars=120,
        max_text_node_chars=20,
    )

    cleaned = cleaner.clean(xhtml, options)
    assert len(cleaned) <= 120
    assert "<script" not in cleaned


def test_noop_limits_paths():
    cleaner = XhtmlCleaner()
    doc = lxml_html.document_fromstring("<html><body><p>a</p></body></html>")

    cleaner._cap_text_content(doc, 0)
    assert doc.xpath("string(//p)") == "a"

    before = lxml_html.tostring(doc, encoding="unicode", method="xml")
    cleaner._trim_elements_to_size(doc, 0)
    after = lxml_html.tostring(doc, encoding="unicode", method="xml")
    assert before == after
