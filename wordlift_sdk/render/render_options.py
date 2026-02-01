"""Render options for HTML to XHTML pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RenderOptions:
    url: str
    headless: bool = True
    timeout_ms: int = 30000
    wait_until: str = "networkidle"
    locale: str = "en-US"
    user_agent: str | None = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    viewport_width: int = 1365
    viewport_height: int = 768
    ignore_https_errors: bool = False
