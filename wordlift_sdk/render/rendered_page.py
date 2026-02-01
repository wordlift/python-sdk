"""Rendered page data returned by the renderer."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RenderedPage:
    html: str
    xhtml: str
    status_code: int | None = None
    resources: list[dict] = field(default_factory=list)
