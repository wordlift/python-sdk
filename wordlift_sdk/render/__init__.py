"""Render and XHTML cleanup utilities."""

from __future__ import annotations

from .cleanup_options import CleanupOptions
from .html_renderer import HtmlRenderer
from .render_options import RenderOptions
from .rendered_page import RenderedPage
from .xhtml_cleaner import XhtmlCleaner


def render_html(options: RenderOptions) -> RenderedPage:
    """Wrapper for backward compatibility."""
    return HtmlRenderer().render(options)


def clean_xhtml(xhtml: str, options: CleanupOptions) -> str:
    """Wrapper for backward compatibility."""
    return XhtmlCleaner().clean(xhtml, options)


__all__ = [
    "CleanupOptions",
    "HtmlRenderer",
    "RenderOptions",
    "RenderedPage",
    "XhtmlCleaner",
    "clean_xhtml",
    "render_html",
]
