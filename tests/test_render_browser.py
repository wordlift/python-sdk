from __future__ import annotations

import pytest

import wordlift_sdk.render.browser as browser_module
from wordlift_sdk.render.browser import Browser, BrowserOperationError
from wordlift_sdk.render.network_policy import (
    GOOGLE_ANALYTICS_URL_PATTERN,
    build_blocked_url_patterns,
)


class _FakePage:
    def __init__(self, should_raise=False, error_message="boom"):
        self._handlers = {}
        self._should_raise = should_raise
        self._error_message = error_message
        self.routes = []

    def on(self, name, handler):
        self._handlers[name] = handler

    def route(self, pattern, handler):
        self.routes.append((pattern, handler))

    def goto(self, url, wait_until, timeout):
        if self._should_raise:
            raise browser_module.PlaywrightError(self._error_message)

        class _Req:
            resource_type = "document"

        response = type(
            "_Resp",
            (),
            {"request": _Req(), "url": url, "status": 200},
        )()

        self._handlers["response"](response)
        return response


class _FakeCdpSession:
    def __init__(self):
        self.sent = []

    def send(self, method, params=None):
        self.sent.append((method, params))


class _FakeContext:
    def __init__(self):
        self.closed = False
        self.script = None
        self.page = _FakePage()
        self.cdp = _FakeCdpSession()
        self.events = []
        self._page_handlers = []

    def on(self, event, handler):
        if event == "page":
            self._page_handlers.append(handler)

    def new_cdp_session(self, page):
        return self.cdp

    def add_init_script(self, script):
        self.script = script

    def new_page(self):
        self.events.append("new_page")
        for handler in self._page_handlers:
            handler(self.page)
        return self.page

    def close(self):
        self.closed = True


class _FakeBrowser:
    def __init__(self, engine="chromium"):
        self.closed = False
        self.kwargs = None
        self.context = _FakeContext()
        self.browser_type = type("_Type", (), {"name": engine})()

    def new_context(self, **kwargs):
        self.kwargs = kwargs
        return self.context

    def close(self):
        self.closed = True


class _FakePlaywright:
    def __init__(self, engine="chromium"):
        self.chromium = self
        self.browser = _FakeBrowser(engine)
        self.stopped = False

    def launch(self, headless):
        return self.browser

    def stop(self):
        self.stopped = True


class _Manager:
    def __init__(self, pw):
        self.pw = pw

    def start(self):
        return self.pw


def test_browser_enter_requires_playwright(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(browser_module, "sync_playwright", None)
    with pytest.raises(RuntimeError, match="Playwright is not installed"):
        Browser(headless=True, timeout_ms=100, wait_until="load").__enter__()


def test_browser_enter_exit_and_open(monkeypatch: pytest.MonkeyPatch):
    pw = _FakePlaywright()
    monkeypatch.setattr(browser_module, "sync_playwright", lambda: _Manager(pw))

    with Browser(
        headless=False,
        timeout_ms=100,
        wait_until="domcontentloaded",
        locale="en-US",
        user_agent="UA",
        viewport_width=1200,
        viewport_height=700,
        ignore_https_errors=True,
    ) as browser:
        page, response, elapsed, resources = browser.open("https://example.org")

        assert page is not None
        assert response is not None
        assert elapsed >= 0
        assert resources and resources[0]["resource_type"] == "document"
        assert pw.browser.kwargs["user_agent"] == "UA"
        assert pw.browser.kwargs["viewport"]["width"] == 1200
        assert pw.browser.kwargs["ignore_https_errors"] is True
        assert pw.browser.kwargs["service_workers"] == "block"
        assert pw.browser.context.events == ["new_page"]
        assert ("Network.setBlockedURLs", {"urls": build_blocked_url_patterns()}) in (
            pw.browser.context.cdp.sent
        )

    assert pw.browser.context.closed is True
    assert pw.browser.closed is True
    assert pw.stopped is True


def test_browser_open_handles_playwright_error(monkeypatch: pytest.MonkeyPatch):
    pw = _FakePlaywright()
    pw.browser.context.page = _FakePage(should_raise=True, error_message="boom")
    monkeypatch.setattr(browser_module, "sync_playwright", lambda: _Manager(pw))

    with Browser(headless=True, timeout_ms=50, wait_until="load") as browser:
        with pytest.raises(BrowserOperationError) as exc:
            browser.open("https://example.org")
        assert exc.value.phase == "navigate"


def test_browser_open_timeout_returns_partial_page(monkeypatch: pytest.MonkeyPatch):
    pw = _FakePlaywright()
    pw.browser.context.page = _FakePage(
        should_raise=True, error_message="Timeout 60000ms exceeded while navigating"
    )
    monkeypatch.setattr(browser_module, "sync_playwright", lambda: _Manager(pw))

    with Browser(
        headless=True, timeout_ms=50, wait_until="domcontentloaded"
    ) as browser:
        page, response, elapsed, resources = browser.open("https://example.org")
        assert page is not None
        assert response is None
        assert elapsed >= 0
        assert resources == []


def test_browser_open_requires_initialized_context():
    browser = Browser(headless=True, timeout_ms=50, wait_until="load")
    with pytest.raises(RuntimeError, match="not initialized"):
        browser.open("https://example.org")


def test_pages_the_site_opens_are_covered(monkeypatch: pytest.MonkeyPatch):
    # A popup the page opens itself is a new page in the same context, and the
    # policy has to reach it too -- not just the page `open()` creates.
    pw = _FakePlaywright()
    monkeypatch.setattr(browser_module, "sync_playwright", lambda: _Manager(pw))

    with Browser(headless=True, timeout_ms=100, wait_until="load"):
        context = pw.browser.context
        context.cdp.sent.clear()
        for handler in context._page_handlers:
            handler(_FakePage())

    assert ("Network.setBlockedURLs", {"urls": build_blocked_url_patterns()}) in (
        context.cdp.sent
    )


def test_non_chromium_engines_use_the_route_fallback(monkeypatch: pytest.MonkeyPatch):
    pw = _FakePlaywright(engine="firefox")
    monkeypatch.setattr(browser_module, "sync_playwright", lambda: _Manager(pw))

    with Browser(headless=True, timeout_ms=100, wait_until="load") as browser:
        browser.open("https://example.org")

    context = pw.browser.context
    assert [pattern for pattern, _ in context.page.routes] == [
        GOOGLE_ANALYTICS_URL_PATTERN
    ]
    assert context.cdp.sent == []
