"""Rendering and cleanup pipeline."""

from __future__ import annotations

from typing import Callable

from wordlift_sdk.render import CleanupOptions, RenderOptions, clean_xhtml, render_html


class RenderPipeline:
    """Renders a page and cleans XHTML for structured data generation."""

    def __init__(
        self,
        headed: bool,
        timeout_ms: int,
        wait_until: str,
        max_xhtml_chars: int,
        max_text_node_chars: int,
    ) -> None:
        self._headed = headed
        self._timeout_ms = timeout_ms
        self._wait_until = wait_until
        self._max_xhtml_chars = max_xhtml_chars
        self._max_text_node_chars = max_text_node_chars

    def render(self, url: str, log: Callable[[str], None]) -> tuple[object, str]:
        log("Rendering page with Playwright...")
        render_options = RenderOptions(
            url=url,
            headless=not self._headed,
            timeout_ms=self._timeout_ms,
            wait_until=self._wait_until,
        )
        rendered = render_html(render_options)

        log("Cleaning XHTML for prompt usage...")
        cleanup_options = CleanupOptions(
            max_xhtml_chars=self._max_xhtml_chars,
            max_text_node_chars=self._max_text_node_chars,
        )
        cleaned_xhtml = clean_xhtml(rendered.xhtml, cleanup_options)
        return rendered, cleaned_xhtml
