from __future__ import annotations

import asyncio
import threading
from io import BytesIO
from types import SimpleNamespace

import pytest

from wordlift_sdk.ingestion.errors import LoaderConfigError, LoaderRuntimeError
from wordlift_sdk.ingestion.loaders import (
    PassthroughLoaderAdapter,
    PlaywrightLoaderAdapter,
    PremiumScraperLoaderAdapter,
    ProxyLoaderAdapter,
    SimpleLoaderAdapter,
    WebScrapeApiLoaderAdapter,
)
from wordlift_sdk.ingestion.models import SourceItem
from wordlift_sdk.ingestion.resolver import ResolvedIngestionConfig
from wordlift_sdk.render.browser import BrowserOperationError
from wordlift_sdk.render.html_renderer import RenderOperationError


def _config(**kwargs) -> ResolvedIngestionConfig:
    defaults = {
        "source_name": "urls",
        "loader_name": "web_scrape_api",
        "passthrough_when_html": True,
        "timeout_ms": 30000,
        "retry_attempts": 1,
        "retry_backoff_ms": 1,
        "source_config": {},
        "loader_config": {
            "client_configuration": object(),
            "render_js": None,
            "wait_for": None,
            "country_code": None,
            "premium_proxy": None,
            "block_ads": None,
        },
        "warnings": tuple(),
    }
    defaults.update(kwargs)
    return ResolvedIngestionConfig(**defaults)


def test_passthrough_loader_requires_html() -> None:
    loader = PassthroughLoaderAdapter()
    with pytest.raises(LoaderRuntimeError) as exc:
        loader.load(SourceItem(id="1", url="https://example.com", html=None), _config())
    assert exc.value.code == "INGEST_LOAD_PASSTHROUGH_MISSING_HTML"


def test_web_scrape_api_loader_emits_required_fetch_meta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = WebScrapeApiLoaderAdapter(mode="default")

    async def fake_scrape_async(**kwargs):
        del kwargs
        return SimpleNamespace(
            id="req-123",
            status="ok",
            errors={"provider": "none"},
            web_page=SimpleNamespace(
                url="https://example.com/final",
                html="<html>ok</html>",
                status_code=200,
            ),
        )

    monkeypatch.setattr(loader, "_scrape_async", fake_scrape_async)

    page = loader.load(
        SourceItem(id="1", url="https://example.com/source"),
        _config(),
    )

    assert page.fetch_meta["backend"] == "web_scrape_api"
    assert page.fetch_meta["request_id"] == "req-123"
    assert page.fetch_meta["provider_status"] == "ok"
    assert page.fetch_meta["provider_details"] == {"provider": "none"}
    assert page.final_url == "https://example.com/final"


def test_simple_loader_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    loader = SimpleLoaderAdapter()

    class _Resp(BytesIO):
        status = 200

        def __init__(self) -> None:
            super().__init__(b"<html>ok</html>")

        def geturl(self) -> str:
            return "https://example.com/final"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: _Resp())

    page = loader.load(SourceItem(id="1", url="https://example.com"), _config())
    assert page.status_code == 200
    assert page.final_url == "https://example.com/final"
    assert page.fetch_meta["backend"] == "simple"


def test_playwright_loader_raises_typed_error_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = PlaywrightLoaderAdapter()
    monkeypatch.setattr(
        loader,
        "_renderer",
        SimpleNamespace(
            render=lambda options: (_ for _ in ()).throw(
                RuntimeError("Playwright is not installed.")
            )
        ),
    )
    with pytest.raises(LoaderConfigError) as exc:
        loader.load(SourceItem(id="1", url="https://example.com"), _config())
    assert exc.value.code == "INGEST_LOAD_PLAYWRIGHT_UNAVAILABLE"


def test_playwright_loader_success_returns_loaded_page() -> None:
    loader = PlaywrightLoaderAdapter()
    url = "https://www.bluehost.com/vps-hosting/docker"
    loader._renderer = SimpleNamespace(
        render=lambda _options: SimpleNamespace(
            status_code=200,
            html="<html>ok</html>",
            resources=[{"url": url, "status": 200}],
        )
    )

    page = loader.load(
        SourceItem(id="1", url=url),
        _config(loader_name="playwright"),
    )

    assert page.item_id == "1"
    assert page.url == url
    assert page.final_url == url
    assert page.status_code == 200
    assert page.html == "<html>ok</html>"
    assert page.fetch_meta["backend"] == "playwright"
    assert page.fetch_meta["resources"] == [{"url": url, "status": 200}]


def test_playwright_loader_offloads_render_when_event_loop_is_active() -> None:
    loader = PlaywrightLoaderAdapter()
    main_thread_id = threading.get_ident()
    seen_thread_ids: list[int] = []

    def _render(_options):
        seen_thread_ids.append(threading.get_ident())
        return SimpleNamespace(status_code=200, html="<html>ok</html>", resources=[])

    loader._renderer = SimpleNamespace(render=_render)
    cfg = _config(loader_name="playwright")

    async def _run() -> None:
        page = loader.load(SourceItem(id="1", url="https://example.com"), cfg)
        assert page.fetch_meta["backend"] == "playwright"

    asyncio.run(_run())

    assert len(seen_thread_ids) == 1
    assert seen_thread_ids[0] != main_thread_id


def test_playwright_loader_navigation_failure_includes_root_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = PlaywrightLoaderAdapter()

    def _raise(_options):
        raise BrowserOperationError(
            "navigate", "Failed to navigate to page: https://example.com"
        ) from TimeoutError("Navigation timeout")

    monkeypatch.setattr(loader, "_renderer", SimpleNamespace(render=_raise))

    cfg = _config(
        loader_name="playwright",
        timeout_ms=45000,
        retry_attempts=1,
        loader_config={"headless": False, "wait_until": "domcontentloaded"},
    )
    with pytest.raises(LoaderRuntimeError) as exc:
        loader.load(SourceItem(id="1", url="https://example.com"), cfg)

    assert exc.value.code == "INGEST_LOAD_BROWSER_ERROR"
    assert str(exc.value) == "Playwright loader failed for https://example.com"
    assert exc.value.details["phase"] == "navigate"
    assert exc.value.details["root_exception_type"] == "TimeoutError"
    assert exc.value.details["root_exception_message"] == "Navigation timeout"
    assert exc.value.details["url"] == "https://example.com"
    assert exc.value.details["wait_until"] == "domcontentloaded"
    assert exc.value.details["timeout_ms"] == 45000
    assert exc.value.details["headless"] is False


def test_playwright_loader_content_failure_includes_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = PlaywrightLoaderAdapter()

    def _raise(_options):
        raise RenderOperationError(
            "content", "Failed to extract page content after retries"
        ) from RuntimeError("content() failed")

    monkeypatch.setattr(loader, "_renderer", SimpleNamespace(render=_raise))

    cfg = _config(
        loader_name="playwright",
        retry_attempts=1,
        loader_config={"headless": True, "wait_until": "networkidle"},
    )
    with pytest.raises(LoaderRuntimeError) as exc:
        loader.load(SourceItem(id="1", url="https://example.com"), cfg)

    assert exc.value.code == "INGEST_LOAD_BROWSER_ERROR"
    assert exc.value.details["phase"] == "content"
    assert exc.value.details["root_exception_type"] == "RuntimeError"
    assert exc.value.details["root_exception_message"] == "content() failed"


def test_playwright_loader_convert_failure_includes_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = PlaywrightLoaderAdapter()

    def _raise(_options):
        raise RenderOperationError(
            "convert", "Failed to convert rendered HTML to XHTML"
        ) from ValueError("Bad XHTML")

    monkeypatch.setattr(loader, "_renderer", SimpleNamespace(render=_raise))

    cfg = _config(
        loader_name="playwright",
        retry_attempts=1,
        loader_config={"headless": True, "wait_until": "load"},
    )
    with pytest.raises(LoaderRuntimeError) as exc:
        loader.load(SourceItem(id="1", url="https://example.com"), cfg)

    assert exc.value.code == "INGEST_LOAD_BROWSER_ERROR"
    assert exc.value.details["phase"] == "convert"
    assert exc.value.details["root_exception_type"] == "ValueError"
    assert exc.value.details["root_exception_message"] == "Bad XHTML"


@pytest.mark.parametrize(
    ("loader", "backend"),
    [
        (ProxyLoaderAdapter(), "proxy"),
        (PremiumScraperLoaderAdapter(), "premium_scraper"),
    ],
)
def test_proxy_and_premium_loader_backends(
    loader: WebScrapeApiLoaderAdapter,
    backend: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_scrape_async(**kwargs):
        del kwargs
        return SimpleNamespace(
            id="req-x",
            status="ok",
            errors=None,
            web_page=SimpleNamespace(
                url="https://example.com/final",
                html="<html>ok</html>",
                status_code=200,
            ),
        )

    monkeypatch.setattr(loader, "_scrape_async", fake_scrape_async)
    page = loader.load(SourceItem(id="1", url="https://example.com/source"), _config())
    assert page.fetch_meta["backend"] == backend
