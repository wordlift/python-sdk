"""HTML rendering and XHTML conversion."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

from wordlift_sdk.utils import HtmlConverter

from .browser import Browser

from .render_options import RenderOptions
from .rendered_page import RenderedPage


class HtmlRenderer:
    """Renders a web page using a browser and converts it to XHTML."""

    def render(self, options: RenderOptions) -> RenderedPage:
        """
        Render a URL to HTML and XHTML.

        Args:
            options: Configuration for rendering (URL, headless, timeout, etc.).

        Returns:
            A RenderedPage object containing the HTML, XHTML, and status code.
        """
        ignore_https_errors = options.ignore_https_errors or self._is_localhost_url(
            options.url
        )
        with Browser(
            headless=options.headless,
            timeout_ms=options.timeout_ms,
            wait_until=options.wait_until,
            locale=options.locale,
            user_agent=options.user_agent,
            viewport_width=options.viewport_width,
            viewport_height=options.viewport_height,
            ignore_https_errors=ignore_https_errors,
        ) as browser:
            page, response, _elapsed_ms, resources = browser.open(options.url)
            if page is None:
                raise RuntimeError("Failed to open page in browser.")
            try:
                html = self._safe_page_content(page, options.timeout_ms)
            finally:
                page.close()

        xhtml = HtmlConverter().convert(html)

        status_code = None
        if response is not None:
            try:
                status_code = response.status
            except Exception:
                status_code = None
        return RenderedPage(
            html=html, xhtml=xhtml, status_code=status_code, resources=resources
        )

    def _is_localhost_url(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
        except Exception:
            return False
        host = (parsed.hostname or "").lower()
        return host == "localhost" or host.endswith(".localhost")

    def _safe_page_content(self, page: Any, timeout_ms: int, retries: int = 3) -> str:
        for attempt in range(retries + 1):
            try:
                return page.content()
            except Exception:
                if attempt >= retries:
                    raise
                try:
                    page.wait_for_load_state("networkidle", timeout=timeout_ms)
                except Exception:
                    try:
                        page.wait_for_load_state("load", timeout=timeout_ms)
                    except Exception:
                        pass
                time.sleep(0.2)
        return page.content()
