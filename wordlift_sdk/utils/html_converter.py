"""HTML to XHTML conversion utility."""

from __future__ import annotations

import re
from typing import Any

_INVALID_XML_CHARS_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
_XML_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:-]*$")


class HtmlConverter:
    """Converts HTML to XHTML."""

    def convert(self, html: str) -> str:
        """
        Convert an HTML string to a valid XHTML string.

        Args:
            html: The raw HTML string.

        Returns:
            A sanitized XHTML string.
        """
        html = re.sub(r"<!DOCTYPE[^>]*>", "", html, flags=re.IGNORECASE)
        html = self._strip_invalid_xml_chars(html)
        try:
            from lxml import html as lxml_html
        except ImportError as exc:
            raise ImportError(
                "lxml is required for XHTML output. Install with: pip install lxml"
            ) from exc

        try:
            parser = lxml_html.HTMLParser(encoding="utf-8", recover=True)
            doc = lxml_html.document_fromstring(html, parser=parser)
            self._sanitize_xhtml_tree(doc)
            xhtml = lxml_html.tostring(doc, encoding="unicode", method="xml")
            return self._strip_invalid_xml_chars(xhtml)
        except Exception as exc:
            raise RuntimeError("Failed to convert HTML to XHTML.") from exc

    def _strip_invalid_xml_chars(self, value: str) -> str:
        return _INVALID_XML_CHARS_RE.sub("", value)

    def _sanitize_xhtml_tree(self, doc: Any) -> None:
        for element in doc.iter():
            if not hasattr(element, "attrib"):
                continue
            for attr in list(element.attrib):
                if not _XML_NAME_RE.match(attr):
                    del element.attrib[attr]
                    continue
                value = element.attrib.get(attr)
                if isinstance(value, str):
                    element.attrib[attr] = self._strip_invalid_xml_chars(value)
