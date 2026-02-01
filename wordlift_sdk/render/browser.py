"""Browser helper for rendering pages with Playwright."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from time import perf_counter

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - runtime dependency
    sync_playwright = None
    PlaywrightError = Exception


@dataclass
class PageFetch:
    response: object | None
    elapsed_ms: float
    resources: list[dict]


class Browser(AbstractContextManager):
    _DEFAULT_HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://wordlift.io",
        "Upgrade-Insecure-Requests": "1",
        "Sec-CH-UA": '"Not A(Brand";v="99", "Chromium";v="120", "Google Chrome";v="120"',
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": '"macOS"',
    }

    def __init__(
        self,
        *,
        headless: bool,
        timeout_ms: int,
        wait_until: str,
        locale: str | None = None,
        user_agent: str | None = None,
        viewport_width: int | None = None,
        viewport_height: int | None = None,
        ignore_https_errors: bool = False,
    ) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.wait_until = wait_until
        self.locale = locale
        self.user_agent = user_agent
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.ignore_https_errors = ignore_https_errors
        self._playwright = None
        self._browser = None
        self._context = None

    def __enter__(self) -> "Browser":
        if sync_playwright is None:
            raise RuntimeError(
                "Playwright is not installed. Run: uv pip install playwright && playwright install"
            )
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        context_kwargs: dict[str, object] = {}
        context_kwargs["locale"] = self.locale or "en-US"
        context_kwargs["timezone_id"] = "America/New_York"
        if self.user_agent:
            context_kwargs["user_agent"] = self.user_agent
        if self.viewport_width and self.viewport_height:
            viewport = {"width": self.viewport_width, "height": self.viewport_height}
        else:
            viewport = {"width": 1365, "height": 768}
        context_kwargs["viewport"] = viewport
        context_kwargs["ignore_https_errors"] = self.ignore_https_errors
        context_kwargs["extra_http_headers"] = dict(self._DEFAULT_HEADERS)
        self._context = self._browser.new_context(**context_kwargs)
        self._context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            window.chrome = window.chrome || { runtime: {} };
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : originalQuery(parameters)
            );
            """
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    def open(self, url: str) -> tuple[object | None, object | None, float, list[dict]]:
        if self._context is None:
            raise RuntimeError("Browser not initialized")
        page = self._context.new_page()
        resources: list[dict] = []

        def handle_response(resp) -> None:
            try:
                request = resp.request
                resources.append(
                    {
                        "url": resp.url,
                        "status": resp.status,
                        "resource_type": request.resource_type,
                    }
                )
            except Exception:
                return

        page.on("response", handle_response)
        start = perf_counter()
        response = None
        try:
            response = page.goto(
                url, wait_until=self.wait_until, timeout=self.timeout_ms
            )
        except PlaywrightError:
            pass
        elapsed_ms = (perf_counter() - start) * 1000
        return page, response, elapsed_ms, resources
