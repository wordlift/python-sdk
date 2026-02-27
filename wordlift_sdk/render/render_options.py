"""Render options for HTML to XHTML pipeline."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_ACCEPT_HEADER = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,*/*;q=0.8"
)
DEFAULT_ACCEPT_LANGUAGE_HEADER = "en-US,en;q=0.9"
DEFAULT_BROWSER_REQUEST_HEADERS = {
    "Accept": DEFAULT_ACCEPT_HEADER,
    "Accept-Language": DEFAULT_ACCEPT_LANGUAGE_HEADER,
    "Referer": "https://wordlift.io",
    "Upgrade-Insecure-Requests": "1",
    "Sec-CH-UA": '"Not A(Brand";v="99", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"macOS"',
}


def build_browser_like_headers(user_agent: str = DEFAULT_USER_AGENT) -> dict[str, str]:
    headers = dict(DEFAULT_BROWSER_REQUEST_HEADERS)
    headers["User-Agent"] = user_agent
    return headers


@dataclass
class RenderOptions:
    url: str
    headless: bool = True
    timeout_ms: int = 30000
    wait_until: str = "domcontentloaded"
    locale: str = "en-US"
    user_agent: str | None = DEFAULT_USER_AGENT
    viewport_width: int = 1365
    viewport_height: int = 768
    ignore_https_errors: bool = False
