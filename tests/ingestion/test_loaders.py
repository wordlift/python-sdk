from __future__ import annotations

import asyncio
import threading
import time
import urllib.error
from io import BytesIO
from types import SimpleNamespace

import pytest
from wordlift_client.models.fetch_js_render_mode import FetchJsRenderMode
from wordlift_client.models.proxy_mode import ProxyMode

from wordlift_sdk.ingestion.errors import LoaderConfigError, LoaderRuntimeError
import wordlift_sdk.ingestion.loaders as loaders_module
from wordlift_sdk.ingestion.loaders import (
    BaseLoaderAdapter,
    CrawlerLoaderAdapter,
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
from wordlift_sdk.render.render_options import build_browser_like_headers


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
        "url_regex": None,
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
    observed: dict[str, object] = {}

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

    def _urlopen(request, timeout):
        observed["request_headers"] = {
            key.lower(): value for key, value in dict(request.header_items()).items()
        }
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)

    page = loader.load(SourceItem(id="1", url="https://example.com"), _config())
    assert page.status_code == 200
    assert page.final_url == "https://example.com/final"
    assert page.fetch_meta["backend"] == "simple"
    assert observed["request_headers"] == {
        key.lower(): value for key, value in build_browser_like_headers().items()
    }


def test_simple_loader_adapter_wraps_url_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = SimpleLoaderAdapter()
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: (_ for _ in ()).throw(urllib.error.URLError("down")),
    )
    with pytest.raises(LoaderRuntimeError) as exc:
        loader.load(
            SourceItem(id="1", url="https://example.com"),
            _config(retry_attempts=1),
        )
    assert exc.value.code == "INGEST_LOAD_NETWORK_ERROR"
    assert exc.value.details["url"] == "https://example.com"


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


def test_run_in_worker_thread_raises_on_hard_timeout() -> None:
    with pytest.raises(LoaderRuntimeError) as exc:
        loaders_module._run_in_worker_thread(lambda: time.sleep(10), timeout=0.05)

    assert exc.value.code == "INGEST_LOAD_BROWSER_TIMEOUT"
    assert exc.value.retryable is True


def test_playwright_loader_wraps_non_runtime_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = PlaywrightLoaderAdapter()

    def _raise(_options):
        raise ValueError("unexpected")

    monkeypatch.setattr(loader, "_renderer", SimpleNamespace(render=_raise))
    with pytest.raises(LoaderRuntimeError) as exc:
        loader.load(
            SourceItem(id="1", url="https://example.com"),
            _config(loader_name="playwright", retry_attempts=1),
        )
    assert exc.value.code == "INGEST_LOAD_BROWSER_ERROR"
    assert exc.value.details["phase"] == "unknown"


def test_build_playwright_error_details_and_phase_fallbacks() -> None:
    options = loaders_module.RenderOptions(
        url="https://example.com", timeout_ms=1000, headless=True, wait_until="load"
    )
    err = RuntimeError("root")
    details = loaders_module._build_playwright_error_details(
        item_url="https://example.com", options=options, exc=err
    )
    assert details["phase"] == "unknown"
    assert details["root_exception_type"] == "RuntimeError"

    cyclic = RuntimeError("cycle")
    cyclic.__cause__ = cyclic
    assert loaders_module._root_exception(cyclic) is cyclic
    assert loaders_module._classify_playwright_error_phase(cyclic) == "unknown"


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


def test_base_loader_with_retry_wraps_untyped_exceptions() -> None:
    base = BaseLoaderAdapter()
    attempts = {"count": 0}

    def _boom():
        attempts["count"] += 1
        raise ValueError("x")

    with pytest.raises(LoaderRuntimeError) as exc:
        base._with_retry(_boom, attempts=2, backoff_ms=0)
    assert attempts["count"] == 2
    assert exc.value.code == "INGEST_LOAD_NETWORK_ERROR"


def test_run_coro_sync_in_running_loop_and_error_path() -> None:
    async def _ok():
        return "ok"

    async def _boom():
        raise RuntimeError("fail")

    async def _run() -> tuple[str, str]:
        ok = loaders_module._run_coro_sync(_ok())
        try:
            loaders_module._run_coro_sync(_boom())
            assert False, "expected RuntimeError"
        except RuntimeError as exc:
            return ok, str(exc)

    ok, msg = asyncio.run(_run())
    assert ok == "ok"
    assert "fail" in msg


@pytest.mark.asyncio
async def test_web_scrape_loader_scrape_async_uses_api_client(
    monkeypatch: pytest.MonkeyPatch,
):
    loader = WebScrapeApiLoaderAdapter(mode="default")

    class _Resp:
        pass

    class _Api:
        def __init__(self, client):
            self.client = client

        async def create_web_page_scrape(
            self, web_page_scrape_request, _request_timeout
        ):
            assert web_page_scrape_request.url == "https://example.com"
            assert _request_timeout == 1.0
            return _Resp()

    class _ClientCtx:
        def __init__(self, cfg):
            self.cfg = cfg

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(loaders_module, "ApiClient", _ClientCtx)
    monkeypatch.setattr(loaders_module, "WebPageScrapeApi", _Api)

    resp = await loader._scrape_async(
        item_url="https://example.com",
        timeout_ms=1000,
        client_configuration=object(),
        render_js=None,
        wait_for=None,
        country_code=None,
        premium_proxy=None,
        block_ads=None,
    )
    assert isinstance(resp, _Resp)


def test_web_scrape_loader_missing_config_and_empty_html() -> None:
    loader = WebScrapeApiLoaderAdapter()
    with pytest.raises(LoaderConfigError):
        loader.load(
            SourceItem(id="1", url="https://example.com"),
            _config(loader_config={}),
        )

    async def _fake(**kwargs):
        del kwargs
        return SimpleNamespace(
            web_page=SimpleNamespace(url="https://example.com", html=None)
        )

    loader._scrape_async = _fake
    with pytest.raises(LoaderRuntimeError) as exc:
        loader.load(
            SourceItem(id="1", url="https://example.com"),
            _config(loader_config={"client_configuration": object()}, retry_attempts=1),
        )
    assert exc.value.code == "INGEST_LOAD_REMOTE_API_ERROR"


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


# ---------------------------------------------------------------------------
# _parse_crawler_enum
# ---------------------------------------------------------------------------


def test_parse_crawler_enum_returns_default_for_none() -> None:
    default = FetchJsRenderMode.DISABLED
    result = loaders_module._parse_crawler_enum(
        FetchJsRenderMode, None, default, "crawler_js_render_mode"
    )
    assert result is default


def test_parse_crawler_enum_valid_value() -> None:
    result = loaders_module._parse_crawler_enum(
        FetchJsRenderMode, "auto", FetchJsRenderMode.DISABLED, "crawler_js_render_mode"
    )
    assert result == FetchJsRenderMode.AUTO


def test_parse_crawler_enum_case_insensitive() -> None:
    result = loaders_module._parse_crawler_enum(
        ProxyMode, "  STANDARD  ", ProxyMode.DISABLED, "crawler_proxy_mode"
    )
    assert result == ProxyMode.STANDARD


def test_parse_crawler_enum_invalid_value_raises() -> None:
    with pytest.raises(LoaderConfigError) as exc:
        loaders_module._parse_crawler_enum(
            FetchJsRenderMode,
            "turbo",
            FetchJsRenderMode.DISABLED,
            "crawler_js_render_mode",
        )
    assert exc.value.code == "INGEST_CFG_INVALID_OPTION_COMBINATION"
    assert "turbo" in str(exc.value)
    assert "crawler_js_render_mode" in str(exc.value)


# ---------------------------------------------------------------------------
# CrawlerLoaderAdapter
# ---------------------------------------------------------------------------


def _crawler_config(**overrides) -> ResolvedIngestionConfig:
    cfg = _config(
        loader_name="crawler",
        loader_config={
            "client_configuration": object(),
            "crawler_js_render_mode": None,
            "crawler_proxy_mode": None,
        },
    )
    if overrides:
        merged = dict(cfg.loader_config)
        merged.update(overrides)
        cfg = _config(loader_name="crawler", loader_config=merged)
    return cfg


def test_crawler_loader_missing_client_configuration_raises() -> None:
    loader = CrawlerLoaderAdapter()
    with pytest.raises(LoaderConfigError) as exc:
        loader.load(
            SourceItem(id="1", url="https://example.com"),
            _config(loader_name="crawler", loader_config={}),
        )
    assert exc.value.code == "INGEST_CFG_INVALID_OPTION_COMBINATION"


def test_crawler_loader_success_returns_loaded_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = CrawlerLoaderAdapter()

    async def fake_fetch(**kwargs):
        del kwargs
        return SimpleNamespace(
            html="<html>crawler</html>",
            url_final="https://example.com/final",
            status_code=200,
            from_cache=True,
            error_code=None,
        )

    monkeypatch.setattr(loader, "_fetch_async", fake_fetch)

    page = loader.load(
        SourceItem(id="42", url="https://example.com"), _crawler_config()
    )

    assert page.item_id == "42"
    assert page.url == "https://example.com"
    assert page.final_url == "https://example.com/final"
    assert page.status_code == 200
    assert page.html == "<html>crawler</html>"
    assert page.fetch_meta["backend"] == "crawler"
    assert page.fetch_meta["from_cache"] is True
    assert page.fetch_meta["error_code"] is None


def test_crawler_loader_final_url_falls_back_to_item_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = CrawlerLoaderAdapter()

    async def fake_fetch(**kwargs):
        del kwargs
        return SimpleNamespace(
            html="<html>ok</html>",
            url_final=None,
            status_code=200,
            from_cache=None,
            error_code=None,
        )

    monkeypatch.setattr(loader, "_fetch_async", fake_fetch)

    page = loader.load(
        SourceItem(id="1", url="https://example.com/original"), _crawler_config()
    )
    assert page.final_url == "https://example.com/original"


def test_crawler_loader_empty_html_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = CrawlerLoaderAdapter()

    async def fake_fetch(**kwargs):
        del kwargs
        return SimpleNamespace(html=None, url_final=None, status_code=200)

    monkeypatch.setattr(loader, "_fetch_async", fake_fetch)

    with pytest.raises(LoaderRuntimeError) as exc:
        loader.load(
            SourceItem(id="1", url="https://example.com"),
            _crawler_config(),
        )
    assert exc.value.code == "INGEST_LOAD_REMOTE_API_ERROR"
    assert exc.value.retryable is True


@pytest.mark.asyncio
async def test_crawler_fetch_async_passes_enum_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = CrawlerLoaderAdapter()
    captured: dict = {}

    class _Api:
        def __init__(self, client):
            pass

        async def fetch_page_fetch_get(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(html="<html/>", url_final=None, status_code=200)

    class _ClientCtx:
        def __init__(self, cfg):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(loaders_module, "ApiClient", _ClientCtx)
    monkeypatch.setattr(loaders_module, "FetchApi", _Api)

    await loader._fetch_async(
        item_url="https://example.com",
        timeout_ms=5000,
        client_configuration=object(),
        js_render_mode=FetchJsRenderMode.AUTO,
        proxy_mode=ProxyMode.STANDARD,
    )

    assert captured["url"] == "https://example.com"
    assert captured["js_render_mode"] == FetchJsRenderMode.AUTO
    assert captured["proxy_mode"] == ProxyMode.STANDARD
    assert captured["_request_timeout"] == pytest.approx(5.0)


@pytest.mark.parametrize(
    ("status", "expected_retryable"),
    [
        (500, True),
        (503, True),
        (429, True),
        (403, False),
        (404, False),
    ],
)
@pytest.mark.asyncio
async def test_crawler_fetch_async_api_exception_retryable(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    expected_retryable: bool,
) -> None:
    from wordlift_client.exceptions import ApiException

    loader = CrawlerLoaderAdapter()

    class _Api:
        def __init__(self, client):
            pass

        async def fetch_page_fetch_get(self, **kwargs):
            exc = ApiException(status=status)
            exc.body = "error body"
            raise exc

    class _ClientCtx:
        def __init__(self, cfg):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(loaders_module, "ApiClient", _ClientCtx)
    monkeypatch.setattr(loaders_module, "FetchApi", _Api)

    with pytest.raises(LoaderRuntimeError) as exc:
        await loader._fetch_async(
            item_url="https://example.com",
            timeout_ms=1000,
            client_configuration=object(),
            js_render_mode=FetchJsRenderMode.DISABLED,
            proxy_mode=ProxyMode.DISABLED,
        )

    assert exc.value.code == "INGEST_LOAD_REMOTE_API_ERROR"
    assert exc.value.retryable is expected_retryable
    assert exc.value.details["status"] == status
