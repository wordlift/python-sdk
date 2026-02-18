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
        self._sanitize_element_with_namespaces(doc, inherited_prefixes={"xml"})

    def _sanitize_element_with_namespaces(
        self, element: Any, inherited_prefixes: set[str]
    ) -> None:
        if not hasattr(element, "attrib"):
            return

        declared = self._declared_prefixes(element)
        in_scope = inherited_prefixes | declared | {"xml"}

        tag = getattr(element, "tag", None)
        if isinstance(tag, str) and ":" in tag and not tag.startswith("{"):
            prefix, local = tag.split(":", 1)
            if prefix and prefix not in in_scope:
                element.tag = local

        for attr in list(element.attrib):
            if attr.startswith("{"):
                value = element.attrib.get(attr)
                if isinstance(value, str):
                    element.attrib[attr] = self._strip_invalid_xml_chars(value)
                continue

            if attr == "xmlns" or attr.startswith("xmlns:"):
                value = element.attrib.get(attr)
                if isinstance(value, str):
                    element.attrib[attr] = self._strip_invalid_xml_chars(value)
                continue

            if ":" in attr:
                prefix, _ = attr.split(":", 1)
                if prefix != "xml" and prefix not in in_scope:
                    del element.attrib[attr]
                    continue

            if not _XML_NAME_RE.match(attr):
                del element.attrib[attr]
                continue

            value = element.attrib.get(attr)
            if isinstance(value, str):
                element.attrib[attr] = self._strip_invalid_xml_chars(value)

        for child in list(element):
            self._sanitize_element_with_namespaces(child, inherited_prefixes=in_scope)

    def _declared_prefixes(self, element: Any) -> set[str]:
        declared: set[str] = set()
        for attr in getattr(element, "attrib", {}):
            if attr == "xmlns":
                continue
            if attr.startswith("xmlns:"):
                prefix = attr.split(":", 1)[1]
                if prefix:
                    declared.add(prefix)
        return declared
