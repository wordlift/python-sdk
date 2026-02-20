from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceItem:
    id: str
    url: str
    metadata: dict[str, Any] = field(default_factory=dict)
    html: str | None = None


@dataclass(frozen=True)
class LoadedPage:
    item_id: str
    url: str
    final_url: str | None
    status_code: int | None
    html: str
    fetch_meta: dict[str, Any] = field(default_factory=dict)
