from __future__ import annotations

import pytest

from wordlift_sdk.render.html_renderer import HtmlRenderer


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
    monkeypatch.setattr("wordlift_sdk.render.html_renderer.Browser", _FakeBrowser)
    monkeypatch.setattr(
        "wordlift_sdk.render.html_renderer.HtmlConverter", _FakeConverter
    )

    renderer = HtmlRenderer()
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
