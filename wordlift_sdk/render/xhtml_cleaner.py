"""XHTML cleanup utilities."""

from __future__ import annotations

import re
from typing import Any


from .cleanup_options import CleanupOptions


class XhtmlCleaner:
    """Cleans and optimizes XHTML content."""

    def clean(self, xhtml: str, options: CleanupOptions) -> str:
        """
        Clean an XHTML string based on the provided options.

        Args:
            xhtml: The XHTML string to clean.
            options: Configuration for cleaning (tags to remove, max chars, etc.).

        Returns:
            The cleaned XHTML string.
        """
        try:
            from lxml import html as lxml_html
        except Exception as exc:
            raise RuntimeError(
                "lxml is required for XHTML cleanup. Install with: pip install lxml"
            ) from exc
        parser = lxml_html.HTMLParser(encoding="utf-8", recover=True)
        doc = lxml_html.document_fromstring(xhtml, parser=parser)
        self._strip_unwanted_tags(doc, options.remove_tags)
        self._compact_text_nodes(doc, options.max_text_node_chars)
        self._cap_text_content(doc, options.max_xhtml_chars)
        cleaned = lxml_html.tostring(doc, encoding="unicode", method="xml")
        if len(cleaned) > options.max_xhtml_chars:
            self._trim_elements_to_size(doc, options.max_xhtml_chars)
            cleaned = lxml_html.tostring(doc, encoding="unicode", method="xml")
        return cleaned

    def _strip_unwanted_tags(self, doc: Any, tags: tuple[str, ...]) -> None:
        if not tags:
            return
        tag_expr = " | ".join(f"//{tag}" for tag in tags)
        if not tag_expr:
            return
        for element in doc.xpath(tag_expr):
            parent = element.getparent()
            if parent is not None:
                parent.remove(element)

    def _compact_text(self, value: str | None, max_chars: int) -> str | None:
        if value is None:
            return None
        text = re.sub(r"\s+", " ", value).strip()
        if not text:
            return None
        if max_chars > 0 and len(text) > max_chars:
            if max_chars <= 3:
                text = text[:max_chars]
            else:
                text = text[: max_chars - 3].rstrip() + "..."
        return text

    def _compact_text_nodes(self, doc: Any, max_chars: int) -> None:
        for element in doc.iter():
            if hasattr(element, "text"):
                element.text = self._compact_text(element.text, max_chars)
            if hasattr(element, "tail"):
                element.tail = self._compact_text(element.tail, max_chars)

    def _cap_text_content(self, doc: Any, max_chars: int) -> None:
        if max_chars <= 0:
            return
        remaining = max_chars
        for element in doc.iter():
            if hasattr(element, "text") and element.text:
                if len(element.text) <= remaining:
                    remaining -= len(element.text)
                else:
                    element.text = element.text[: max(0, remaining)].rstrip()
                    remaining = 0
            if remaining <= 0:
                self._clear_text_after(doc, element)
                break
            if hasattr(element, "tail") and element.tail:
                if len(element.tail) <= remaining:
                    remaining -= len(element.tail)
                else:
                    element.tail = element.tail[: max(0, remaining)].rstrip()
                    remaining = 0
            if remaining <= 0:
                self._clear_text_after(doc, element)
                break

    def _clear_text_after(self, doc: Any, stop_element: Any) -> None:
        seen = False
        for element in doc.iter():
            if element is stop_element:
                seen = True
                continue
            if not seen:
                continue
            if hasattr(element, "text") and element.text:
                element.text = None
            if hasattr(element, "tail") and element.tail:
                element.tail = None

    def _trim_elements_to_size(self, doc: Any, max_chars: int) -> None:
        if max_chars <= 0:
            return
        try:
            from lxml import html as lxml_html
        except Exception:
            return
        elements = list(doc.iter())
        for element in reversed(elements):
            parent = element.getparent()
            if parent is None:
                continue
            parent.remove(element)
            current = lxml_html.tostring(doc, encoding="unicode", method="xml")
            if len(current) <= max_chars:
                return
