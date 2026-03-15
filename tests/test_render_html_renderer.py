from __future__ import annotations

import pytest

from wordlift_sdk.render.browser import BrowserOperationError
from wordlift_sdk.render.html_renderer import HtmlRenderer, RenderOperationError


class _FakePage:
    def __init__(self, html: str) -> None:
        self._html = html

    def content(self) -> str:
        return self._html

    def wait_for_load_state(self, *_args, **_kwargs) -> None:
        return None

    def close(self) -> None:
        return None


class _FakeBrowser:
    def __init__(self, *args, **kwargs) -> None:
        self._page = _FakePage("<html><body>Hello</body></html>")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def open(self, url: str):
        return self._page, _FakeResponse(200), 12.0, [{"url": url, "status": 200}]


class _FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status


class _FakeConverter:
    def convert(self, html: str) -> str:
        return html.replace("<body>", "<body data-xhtml='1'>")


def test_html_renderer_uses_browser_and_converter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import wordlift_sdk.render.html_renderer as html_renderer_module

    monkeypatch.setattr("wordlift_sdk.render.html_renderer.Browser", _FakeBrowser)
    monkeypatch.setattr(
        "wordlift_sdk.render.html_renderer.HtmlConverter", _FakeConverter
    )

    renderer = html_renderer_module.HtmlRenderer()
    result = renderer.render(
        options=type(
            "Opt",
            (),
            {
                "url": "https://example.com",
                "headless": True,
                "timeout_ms": 1000,
                "wait_until": "load",
                "locale": "en-US",
                "user_agent": None,
                "viewport_width": 1365,
                "viewport_height": 768,
                "ignore_https_errors": False,
            },
        )()
    )

    assert "data-xhtml='1'" in result.xhtml
    assert result.status_code == 200
    assert result.resources


def test_html_renderer_reraises_browser_operation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import wordlift_sdk.render.html_renderer as html_renderer_module

    class _FailBrowser:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def open(self, url: str):
            raise BrowserOperationError("navigate", "boom")

    monkeypatch.setattr("wordlift_sdk.render.html_renderer.Browser", _FailBrowser)

    renderer = html_renderer_module.HtmlRenderer()
    with pytest.raises(BrowserOperationError):
        renderer.render(
            options=type(
                "Opt",
                (),
                {
                    "url": "https://example.com",
                    "headless": True,
                    "timeout_ms": 1000,
                    "wait_until": "load",
                    "locale": "en-US",
                    "user_agent": None,
                    "viewport_width": 1365,
                    "viewport_height": 768,
                    "ignore_https_errors": False,
                },
            )()
        )


def test_html_renderer_wraps_convert_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    import wordlift_sdk.render.html_renderer as html_renderer_module

    monkeypatch.setattr("wordlift_sdk.render.html_renderer.Browser", _FakeBrowser)

    class _FailConverter:
        def convert(self, html: str) -> str:
            del html
            raise ValueError("bad convert")

    monkeypatch.setattr(
        "wordlift_sdk.render.html_renderer.HtmlConverter", _FailConverter
    )

    renderer = html_renderer_module.HtmlRenderer()
    with pytest.raises(html_renderer_module.RenderOperationError) as exc:
        renderer.render(
            options=type(
                "Opt",
                (),
                {
                    "url": "https://example.com",
                    "headless": True,
                    "timeout_ms": 1000,
                    "wait_until": "load",
                    "locale": "en-US",
                    "user_agent": None,
                    "viewport_width": 1365,
                    "viewport_height": 768,
                    "ignore_https_errors": False,
                },
            )()
        )
    assert exc.value.phase == "convert"


def test_html_renderer_safe_page_content_failure_paths() -> None:
    renderer = HtmlRenderer()

    class _AlwaysFailPage:
        def content(self) -> str:
            raise RuntimeError("content fail")

        def wait_for_load_state(self, *_args, **_kwargs) -> None:
            raise RuntimeError("wait fail")

    with pytest.raises(RenderOperationError) as exc:
        renderer._safe_page_content(_AlwaysFailPage(), timeout_ms=1, retries=0)
    assert exc.value.phase == "content"
