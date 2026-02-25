"""HTML to XHTML conversion utility."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

_XML_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:-]*$")
_XML_CHAR_REF_RE = re.compile(r"&#(x[0-9A-Fa-f]+|[0-9]+);")


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
            xhtml = self._sanitize_serialized_xml(xhtml)
            parse_error = self._validate_xml(xhtml)
            if parse_error is None:
                return xhtml

            fallback_doc = lxml_html.document_fromstring(xhtml, parser=parser)
            self._sanitize_xhtml_tree(fallback_doc)
            fallback_xhtml = lxml_html.tostring(
                fallback_doc, encoding="unicode", method="xml"
            )
            fallback_xhtml = self._sanitize_serialized_xml(fallback_xhtml)
            fallback_xhtml = self._strip_parse_error_tokens(fallback_xhtml)
            fallback_error = self._validate_xml(fallback_xhtml)
            if fallback_error is None:
                return fallback_xhtml

            context = self._format_parse_error_context(fallback_xhtml, fallback_error)
            raise RuntimeError(
                "Failed to produce XML 1.0-safe XHTML after strict fallback sanitation. "
                f"Parse error: {fallback_error}. Context:\n{context}"
            ) from fallback_error
        except Exception as exc:
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError("Failed to convert HTML to XHTML.") from exc

    def _strip_invalid_xml_chars(self, value: str) -> str:
        return "".join(ch for ch in value if self._is_valid_xml_codepoint(ord(ch)))

    def _strip_invalid_xml_char_refs(self, value: str) -> str:
        def repl(match: re.Match[str]) -> str:
            raw = match.group(1)
            codepoint = int(raw[1:], 16) if raw.startswith("x") else int(raw)
            return match.group(0) if self._is_valid_xml_codepoint(codepoint) else ""

        return _XML_CHAR_REF_RE.sub(repl, value)

    def _sanitize_serialized_xml(self, value: str) -> str:
        return self._strip_invalid_xml_chars(self._strip_invalid_xml_char_refs(value))

    def _is_valid_xml_codepoint(self, codepoint: int) -> bool:
        if codepoint in (0x9, 0xA, 0xD):
            return True
        if 0x20 <= codepoint <= 0xD7FF:
            return True
        if 0xE000 <= codepoint <= 0xFFFD:
            return True
        return 0x10000 <= codepoint <= 0x10FFFF

    def _validate_xml(self, value: str) -> ET.ParseError | None:
        try:
            ET.fromstring(value)
            return None
        except ET.ParseError as exc:
            return exc

    def _strip_parse_error_tokens(self, value: str, max_attempts: int = 12) -> str:
        out = value
        for _ in range(max_attempts):
            error = self._validate_xml(out)
            if error is None:
                return out
            position = getattr(error, "position", None)
            if not position:
                return out
            index = self._line_col_to_index(out, position[0], position[1])
            if index is None or index >= len(out):
                return out
            out = out[:index] + out[index + 1 :]
        return out

    def _line_col_to_index(self, value: str, line: int, col: int) -> int | None:
        if line < 1 or col < 0:
            return None
        current_line = 1
        current_col = 0
        for idx, ch in enumerate(value):
            if current_line == line and current_col == col:
                return idx
            if ch == "\n":
                current_line += 1
                current_col = 0
            else:
                current_col += 1
        if current_line == line and current_col == col:
            return len(value)
        return None

    def _format_parse_error_context(self, value: str, error: ET.ParseError) -> str:
        position = getattr(error, "position", None)
        if not position:
            return "(no line/column position available)"
        line, col = position
        lines = value.splitlines()
        if line < 1 or line > len(lines):
            return f"(line {line} out of range)"
        source_line = lines[line - 1]
        pointer = " " * min(col, len(source_line)) + "^"
        return f"line {line}, column {col}\n{source_line}\n{pointer}"

    def _sanitize_xhtml_tree(self, doc: Any) -> None:
        self._remove_problem_nodes(doc)
        self._sanitize_element_with_namespaces(doc, inherited_prefixes={"xml"})

    def _remove_problem_nodes(self, doc: Any) -> None:
        if not hasattr(doc, "xpath"):
            return
        for query in ("//comment()", "//processing-instruction()"):
            for node in doc.xpath(query):
                parent = node.getparent()
                if parent is not None:
                    parent.remove(node)

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

            if attr == "xmlns":
                # Drop default namespace so plain XPath selectors (.//div) work on __XHTML__.
                del element.attrib[attr]
                continue

            if attr.startswith("xmlns:"):
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

        text = getattr(element, "text", None)
        if isinstance(text, str):
            element.text = self._strip_invalid_xml_chars(text)
        tail = getattr(element, "tail", None)
        if isinstance(tail, str):
            element.tail = self._strip_invalid_xml_chars(tail)

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
