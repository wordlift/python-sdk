from __future__ import annotations

from datetime import datetime
from typing import Any

from wordlift_sdk.ingestion.resolver import ResolvedIngestionConfig

from .url_source import Url, UrlSource


class AdapterUrlSource(UrlSource):
    def __init__(self, adapter: Any, config: ResolvedIngestionConfig):
        self._adapter = adapter
        self._config = config

    async def urls(self):
        for item in self._adapter.iter_items(self._config):
            date_modified = None
            raw_date = item.metadata.get("date_modified")
            if isinstance(raw_date, datetime):
                date_modified = raw_date
            elif isinstance(raw_date, str) and raw_date:
                try:
                    date_modified = datetime.fromisoformat(raw_date)
                except ValueError:
                    date_modified = None
            yield Url(
                value=item.url,
                iri=item.metadata.get("iri"),
                import_hash=(
                    item.metadata.get("import_hash")
                    or item.metadata.get("seovoc:importHash")
                ),
                date_modified=date_modified,
            )
