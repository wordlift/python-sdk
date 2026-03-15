"""Render and XHTML cleanup utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._lazy_exports import resolve_attr

if TYPE_CHECKING:
    from wordlift_sdk.render.cleanup_options import CleanupOptions
    from wordlift_sdk.render.render_options import RenderOptions
    from wordlift_sdk.render.rendered_page import RenderedPage


def render_html(options: RenderOptions) -> RenderedPage:
    """Wrapper for backward compatibility."""
    renderer_class = resolve_attr(
        name="HtmlRenderer",
        module_name="wordlift_sdk.render",
        exports=_EXPORTS,
        extra="render",
    )
    return renderer_class().render(options)


def clean_xhtml(xhtml: str, options: CleanupOptions) -> str:
    """Wrapper for backward compatibility."""
    cleaner_class = resolve_attr(
        name="XhtmlCleaner",
        module_name="wordlift_sdk.render",
        exports=_EXPORTS,
        extra="render",
    )
    return cleaner_class().clean(xhtml, options)


__all__ = [
    "CleanupOptions",
    "HtmlRenderer",
    "RenderOptions",
    "RenderedPage",
    "XhtmlCleaner",
    "clean_xhtml",
    "render_html",
]


_EXPORTS = {
    "CleanupOptions": ("wordlift_sdk.render.cleanup_options", "CleanupOptions"),
    "HtmlRenderer": ("wordlift_sdk.render.html_renderer", "HtmlRenderer"),
    "RenderOptions": ("wordlift_sdk.render.render_options", "RenderOptions"),
    "RenderedPage": ("wordlift_sdk.render.rendered_page", "RenderedPage"),
    "XhtmlCleaner": ("wordlift_sdk.render.xhtml_cleaner", "XhtmlCleaner"),
}


def __getattr__(name: str):
    return resolve_attr(
        name=name,
        module_name="wordlift_sdk.render",
        exports=_EXPORTS,
        extra="render",
    )
