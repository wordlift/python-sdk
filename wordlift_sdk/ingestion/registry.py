from __future__ import annotations

from typing import Generic, TypeVar

from .errors import IngestionConfigError

T = TypeVar("T")


class AdapterRegistry(Generic[T]):
    def __init__(self, *, kind: str) -> None:
        self._kind = kind
        self._entries: dict[str, T] = {}

    def register(self, name: str, adapter: T) -> None:
        key = name.strip().lower()
        if not key:
            raise ValueError("Adapter name cannot be empty")
        self._entries[key] = adapter

    def resolve(self, name: str) -> T:
        key = name.strip().lower()
        if key not in self._entries:
            raise IngestionConfigError(
                f"Unsupported {self._kind}: {name}",
                code=(
                    "INGEST_CFG_UNSUPPORTED_SOURCE"
                    if self._kind == "source"
                    else "INGEST_CFG_UNSUPPORTED_LOADER"
                ),
                details={"supported": sorted(self._entries.keys())},
            )
        return self._entries[key]

    def names(self) -> list[str]:
        return sorted(self._entries.keys())
