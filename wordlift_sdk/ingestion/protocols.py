from __future__ import annotations

from typing import Iterator, Protocol

from .models import LoadedPage, SourceItem


class SourceAdapter(Protocol):
    def iter_items(self, config: "ResolvedIngestionConfig") -> Iterator[SourceItem]: ...


class LoaderAdapter(Protocol):
    def load(
        self, item: SourceItem, config: "ResolvedIngestionConfig"
    ) -> LoadedPage: ...


# Forward reference only for type-checkers.
class ResolvedIngestionConfig(Protocol):
    pass
