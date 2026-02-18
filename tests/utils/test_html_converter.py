"""Tests for the HtmlConverter utility."""

import xml.etree.ElementTree as ET

import pytest

try:
    from lxml import html as lxml_html
except ImportError:
    lxml_html = None

from wordlift_sdk.utils.html_converter import HtmlConverter


class TestHtmlConverter:
    @pytest.fixture
    def converter(self):
        return HtmlConverter()

    def test_convert_valid_html(self, converter):
        """Test conversion of valid HTML to XHTML."""
        if lxml_html is None:
            pytest.skip("lxml not installed")

        html_input = "<html><body><p>Hello World</p></body></html>"
        xhtml_output = converter.convert(html_input)

        assert "<html>" in xhtml_output
        assert "<body>" in xhtml_output
        assert "<p>Hello World</p>" in xhtml_output

        # Check that it parses back as XML (basic check)
        assert xhtml_output.strip().endswith("</html>")

    def test_convert_invalid_html_chars(self, converter):
        """Test stripping of invalid XML characters."""
        if lxml_html is None:
            pytest.skip("lxml not installed")

        # \x00 is invalid in XML 1.0
        html_input = "<html><body><p>Hello\x00World</p></body></html>"
        xhtml_output = converter.convert(html_input)

        assert "HelloWorld" in xhtml_output
        assert "\x00" not in xhtml_output

    def test_convert_sanitize_attributes(self, converter):
        """Test sanitization of attributes with invalid names."""
        if lxml_html is None:
            pytest.skip("lxml not installed")

        # Attribute name starting with number is invalid in XML 1.0
        html_input = '<html><body><div 123attr="value" valid="ok"></div></body></html>'
        xhtml_output = converter.convert(html_input)

        assert 'valid="ok"' in xhtml_output
        assert "123attr" not in xhtml_output

    def test_convert_sanitize_attribute_values(self, converter):
        """Test sanitization of attribute values with invalid characters."""
        if lxml_html is None:
            pytest.skip("lxml not installed")

        html_input = "<html><body><div title='bad\x00value'></div></body></html>"
        xhtml_output = converter.convert(html_input)

        assert 'title="badvalue"' in xhtml_output
        assert "\x00" not in xhtml_output

    def test_conversion_failure(self, converter, monkeypatch):
        """Test handling of conversion failure."""
        if lxml_html is None:
            pytest.skip("lxml not installed")

        # Mock lxml_html.document_fromstring to raise an exception
        def mock_document_fromstring(*args, **kwargs):
            raise Exception("Parsing failed")

        monkeypatch.setattr(lxml_html, "document_fromstring", mock_document_fromstring)

        with pytest.raises(RuntimeError, match="Failed to convert HTML to XHTML"):
            converter.convert("<html></html>")

    def test_convert_strips_undeclared_prefixes_and_preserves_declared_ones(
        self, converter
    ):
        """Undeclared prefixes are stripped/removed while declared ones remain."""
        if lxml_html is None:
            pytest.skip("lxml not installed")

        html_input = """
<html><body>
  <o:p xlink:href="https://example.com" foo:bar="1" xml:lang="en">Hello</o:p>
  <svg:svg xmlns:svg="http://www.w3.org/2000/svg" svg:width="100"></svg:svg>
</body></html>
"""
        xhtml_output = converter.convert(html_input)

        assert "<o:p" not in xhtml_output
        assert "<p" in xhtml_output
        assert "xlink:href=" not in xhtml_output
        assert "foo:bar=" not in xhtml_output
        assert 'xml:lang="en"' in xhtml_output
        assert "svg:svg" in xhtml_output
        assert "svg:width" in xhtml_output

        ET.fromstring(xhtml_output)

    def test_convert_removes_xml_invalid_comments(self, converter):
        """Comments with XML-invalid token patterns are removed."""
        if lxml_html is None:
            pytest.skip("lxml not installed")

        html_input = "<html><body><!--foo--bar--><p>ok</p></body></html>"
        xhtml_output = converter.convert(html_input)

        assert "<!--" not in xhtml_output
        assert "<p>ok</p>" in xhtml_output
        ET.fromstring(xhtml_output)
