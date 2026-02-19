from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class IngestionWarning:
    code: str
    message: str
    new_key: str | None = None
    new_value: Any | None = None
    legacy_key: str | None = None
    legacy_value: Any | None = None
    winner: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_event(self) -> dict[str, Any]:
        payload = {
            "event": "ingest.warning",
            "code": self.code,
            "message": self.message,
            "timestamp": _utc_now_iso(),
            "meta": dict(self.details),
        }
        if self.new_key is not None:
            payload["new_key"] = self.new_key
        if self.new_value is not None:
            payload["new_value"] = self.new_value
        if self.legacy_key is not None:
            payload["legacy_key"] = self.legacy_key
        if self.legacy_value is not None:
            payload["legacy_value"] = self.legacy_value
        if self.winner is not None:
            payload["winner"] = self.winner
        return payload
