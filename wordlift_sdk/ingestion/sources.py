from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator

import advertools as adv
import gspread
import pandas as pd

from wordlift_sdk.render.render_options import build_browser_like_headers
from wordlift_sdk.utils.create_dataframe_from_google_sheets import (
    create_dataframe_from_google_sheets,
)

from .errors import SourceConfigError, SourceRuntimeError
from .models import SourceItem
from .resolver import ResolvedIngestionConfig


def _normalize_url_list(urls_value: Any) -> list[str]:
    if urls_value is None:
        return []
    if isinstance(urls_value, list):
        return [str(u).strip() for u in urls_value if str(u).strip()]
    if isinstance(urls_value, str):
        return [u.strip() for u in re.split(r"[\n,]", urls_value) if u and u.strip()]
    raise SourceConfigError(
        "Invalid URLS format",
        code="INGEST_SRC_INVALID_ITEM",
        details={"type": type(urls_value).__name__},
    )


class UrlListSourceAdapter:
    def iter_items(self, config: ResolvedIngestionConfig) -> Iterator[SourceItem]:
        urls = _normalize_url_list(config.source_config.get("urls"))
        for idx, url in enumerate(urls):
            yield SourceItem(id=f"url:{idx}", url=url)


class SitemapSourceAdapter:
    def iter_items(self, config: ResolvedIngestionConfig) -> Iterator[SourceItem]:
        sitemap_url = config.source_config.get("sitemap_url")
        pattern_raw = config.source_config.get("sitemap_url_pattern")
        pattern = re.compile(pattern_raw) if pattern_raw else None
        request_headers = build_browser_like_headers()

        try:
            sitemap_df = adv.sitemaps.sitemap_to_df(
                sitemap_url=sitemap_url, request_headers=request_headers
            )
        except Exception as exc:
            raise SourceRuntimeError(
                f"Failed to read sitemap: {sitemap_url}",
                code="INGEST_SRC_SITEMAP_READ_FAILED",
                details={"sitemap_url": sitemap_url},
            ) from exc

        if "lastmod" not in sitemap_df.columns:
            sitemap_df["lastmod"] = None
        sitemap_df["lastmod_as_datetime"] = pd.to_datetime(
            sitemap_df["lastmod"], errors="coerce"
        )

        for idx, row in sitemap_df.iterrows():
            url = str(row.get("loc", "")).strip()
            if not url:
                continue
            if pattern and not pattern.search(url):
                continue
            date_modified = row.get("lastmod_as_datetime")
            metadata: dict[str, Any] = {}
            if pd.notna(date_modified):
                metadata["date_modified"] = date_modified.to_pydatetime().isoformat()
            yield SourceItem(id=f"sitemap:{idx}", url=url, metadata=metadata)


class GoogleSheetsSourceAdapter:
    def iter_items(self, config: ResolvedIngestionConfig) -> Iterator[SourceItem]:
        sheets_url = config.source_config.get("sheets_url")
        sheets_name = config.source_config.get("sheets_name")
        sheets_service_account = config.source_config.get("sheets_service_account")

        try:
            creds_or_client = gspread.service_account(filename=sheets_service_account)
        except Exception as exc:
            raise SourceConfigError(
                "Invalid Google Sheets service account configuration",
                code="INGEST_SRC_SHEETS_CONFIG_INVALID",
                details={"sheets_service_account": sheets_service_account},
            ) from exc

        try:
            df = create_dataframe_from_google_sheets(
                creds_or_client, sheets_url, sheets_name
            )
        except Exception as exc:
            raise SourceRuntimeError(
                "Failed to read Google Sheets source",
                code="INGEST_SRC_SHEETS_READ_FAILED",
                details={"sheets_url": sheets_url, "sheets_name": sheets_name},
            ) from exc

        if "url" not in df.columns:
            raise SourceConfigError(
                "The Google Sheet must contain a 'url' column",
                code="INGEST_SRC_SHEETS_CONFIG_INVALID",
                details={"required_column": "url"},
            )

        for idx, row in df.iterrows():
            raw_url = row.get("url")
            if pd.isna(raw_url):
                continue
            url = str(raw_url).strip()
            if not url:
                continue
            metadata = {
                k: v
                for k, v in row.to_dict().items()
                if k != "url" and not (isinstance(v, float) and pd.isna(v))
            }
            yield SourceItem(id=f"sheets:{idx}", url=url, metadata=metadata)


class LocalSourceAdapter:
    def iter_items(self, config: ResolvedIngestionConfig) -> Iterator[SourceItem]:
        items = config.source_config.get("items")
        file_path = config.source_config.get("file")

        if items is None and file_path is None:
            raise SourceConfigError(
                "Local source requires INGEST_LOCAL_ITEMS or INGEST_LOCAL_FILE",
                code="INGEST_SRC_LOCAL_FILE_INVALID",
            )

        if items is None:
            items = self._load_file(file_path)

        if not isinstance(items, list):
            raise SourceConfigError(
                "Local source items must be a list",
                code="INGEST_SRC_INVALID_ITEM",
                details={"type": type(items).__name__},
            )

        for idx, raw in enumerate(items):
            if not isinstance(raw, dict):
                raise SourceConfigError(
                    "Local source item must be an object",
                    code="INGEST_SRC_INVALID_ITEM",
                    details={"index": idx},
                )

            item_id = str(raw.get("id") or f"local:{idx}")
            url = str(raw.get("url") or "").strip()
            html = raw.get("html")
            metadata = raw.get("metadata") or {}

            if not isinstance(metadata, dict):
                raise SourceConfigError(
                    "Local source metadata must be an object",
                    code="INGEST_SRC_INVALID_ITEM",
                    details={"index": idx},
                )

            if not url and not item_id:
                raise SourceConfigError(
                    "Local source item requires at least id or url",
                    code="INGEST_SRC_INVALID_ITEM",
                    details={"index": idx},
                )

            effective_url = url or f"local://{item_id}"
            yield SourceItem(
                id=item_id,
                url=effective_url,
                metadata=metadata,
                html=None if html is None else str(html),
            )

    def _load_file(self, file_path: str) -> list[dict[str, Any]]:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise SourceConfigError(
                "Local source file does not exist",
                code="INGEST_SRC_LOCAL_FILE_INVALID",
                details={"file": file_path},
            )

        if path.suffix.lower() == ".jsonl":
            rows: list[dict[str, Any]] = []
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
            return rows

        if path.suffix.lower() == ".json":
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                return loaded
            raise SourceConfigError(
                "Local JSON source must be a list",
                code="INGEST_SRC_LOCAL_FILE_INVALID",
                details={"file": file_path},
            )

        raise SourceConfigError(
            "Unsupported local file format (use .json or .jsonl)",
            code="INGEST_SRC_LOCAL_FILE_INVALID",
            details={"file": file_path},
        )


__all__ = [
    "GoogleSheetsSourceAdapter",
    "LocalSourceAdapter",
    "SitemapSourceAdapter",
    "UrlListSourceAdapter",
]
