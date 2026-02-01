"""Cleanup options for XHTML sanitization."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CleanupOptions:
    max_xhtml_chars: int = 40000
    max_text_node_chars: int = 400
    remove_tags: tuple[str, ...] = (
        "script",
        "style",
        "noscript",
        "svg",
        "canvas",
        "iframe",
        "form",
        "input",
        "button",
        "nav",
        "aside",
    )
