from __future__ import annotations

import asyncio
import functools
import json
import logging
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from wordlift_client import WebPage, WebPageScrapeResponse

from wordlift_sdk.ingestion import run_ingestion

from ...configuration import ConfigurationProvider
from ...protocol import Context, WebPageImportProtocolInterface
from ...url_source import Url
from .url_handler import UrlHandler

logger = logging.getLogger(__name__)
_DIAG_KEYS = (
    "phase",
    "root_exception_type",
    "root_exception_message",
    "url",
    "wait_until",
    "timeout_ms",
    "headless",
)
_MAX_ROOT_MESSAGE_LEN = 2048
_MAX_DIAGNOSTICS_LEN = 3072
_REDACT_KEYS = ("token", "secret", "password", "cookie", "authorization", "api_key")


class IngestionWebPageScrapeUrlHandler(UrlHandler):
    def __init__(
        self,
        context: Context,
        configuration_provider: ConfigurationProvider,
        web_page_scrape_callback: WebPageImportProtocolInterface,
    ) -> None:
        self._context = context
        self._configuration_provider = configuration_provider
        self._web_page_scrape_callback = web_page_scrape_callback

    async def __call__(self, url: Url) -> None:
        settings = self._build_settings(url)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, functools.partial(run_ingestion, settings)
        )

        if not result.pages:
            failed = [
                e for e in result.events if e.get("event") == "ingest.item_failed"
            ]
            if failed:
                first = failed[0]
                base_message = f"Ingestion loader failed for {url.value}: {first.get('code')} {first.get('message')}"
                diagnostics = _format_failure_diagnostics(first.get("meta"))
                error_message = (
                    f"{base_message} diagnostics={diagnostics}"
                    if diagnostics is not None
                    else base_message
                )
                logger.error(error_message)
                raise RuntimeError(error_message)
            raise RuntimeError(f"Ingestion loader produced no page for {url.value}")

        page = result.pages[0]
        # Do not emit callback imports for HTTP error pages even when HTML exists.
        if _is_http_error_status(page.status_code):
            message = (
                f"Ingestion loader returned HTTP error status for {url.value}: "
                f"status_code={page.status_code} final_url={page.final_url or page.url}"
            )
            logger.error(message)
            raise RuntimeError(message)

        response = WebPageScrapeResponse(
            web_page=WebPage(
                url=page.final_url or page.url,
                html=page.html,
                status_code=page.status_code,
            )
        )
        await self._web_page_scrape_callback.callback(
            response,
            existing_web_page_id=url.iri,
            existing_import_hash=url.import_hash,
        )

    def _build_settings(self, url: Url) -> dict[str, Any]:
        keys = [
            "WORDLIFT_KEY",
            "API_URL",
            "SSL_CA_CERT",
            "INGEST_LOADER",
            "INGEST_PASSTHROUGH_WHEN_HTML",
            "INGEST_TIMEOUT_MS",
            "INGEST_RETRY_ATTEMPTS",
            "INGEST_RETRY_BACKOFF_MS",
            "WEB_PAGE_IMPORT_RENDER_JS",
            "WEB_PAGE_IMPORT_WAIT_FOR",
            "WEB_PAGE_IMPORT_COUNTRY_CODE",
            "WEB_PAGE_IMPORT_PREMIUM_PROXY",
            "WEB_PAGE_IMPORT_BLOCK_ADS",
            "PLAYWRIGHT_WAIT_UNTIL",
            "PLAYWRIGHT_HEADLESS",
        ]
        settings = {
            key: self._configuration_provider.get_value(key)
            for key in keys
            if self._configuration_provider.get_value(key) is not None
        }
        settings["INGEST_SOURCE"] = "local"
        settings["INGEST_LOCAL_ITEMS"] = [
            {
                "id": url.iri or url.value,
                "url": url.value,
            }
        ]
        return settings


def _is_http_error_status(status_code: Any) -> bool:
    if not isinstance(status_code, int):
        return False
    return status_code >= 400


def _format_failure_diagnostics(meta: Any) -> str | None:
    if not isinstance(meta, dict) or not meta:
        return None
    payload: dict[str, Any] = {}
    for key in _DIAG_KEYS:
        value = meta.get(key)
        if value is None:
            continue
        if key == "root_exception_message":
            payload[key] = _truncate(_sanitize_text(str(value)), _MAX_ROOT_MESSAGE_LEN)
            continue
        if key == "url":
            payload[key] = _sanitize_url(str(value))
            continue
        if isinstance(value, str):
            payload[key] = _sanitize_text(value)
            continue
        payload[key] = value

    if not payload:
        return None

    diagnostics = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if len(diagnostics) <= _MAX_DIAGNOSTICS_LEN:
        return diagnostics

    root = payload.get("root_exception_message")
    if isinstance(root, str):
        over_by = len(diagnostics) - _MAX_DIAGNOSTICS_LEN
        payload["root_exception_message"] = _truncate(
            root, max(64, len(root) - over_by - 3)
        )
        diagnostics = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if len(diagnostics) <= _MAX_DIAGNOSTICS_LEN:
            return diagnostics

    url_value = payload.get("url")
    if isinstance(url_value, str):
        over_by = len(diagnostics) - _MAX_DIAGNOSTICS_LEN
        payload["url"] = _truncate(url_value, max(64, len(url_value) - over_by - 3))
        diagnostics = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if len(diagnostics) <= _MAX_DIAGNOSTICS_LEN:
            return diagnostics

    payload["root_exception_message"] = "[truncated]"
    diagnostics = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if len(diagnostics) <= _MAX_DIAGNOSTICS_LEN:
        return diagnostics
    return _truncate(diagnostics, _MAX_DIAGNOSTICS_LEN)


def _truncate(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    if max_len <= 3:
        return value[:max_len]
    return value[: max_len - 3] + "..."


def _sanitize_text(value: str) -> str:
    sanitized = value
    for key in _REDACT_KEYS:
        sanitized = re.sub(
            rf"(?i)({re.escape(key)}\s*[=:]\s*)([^\s,;]+)",
            r"\1[REDACTED]",
            sanitized,
        )
    return sanitized


def _sanitize_url(value: str) -> str:
    try:
        parts = urlsplit(value)
    except Exception:
        return _sanitize_text(value)
    query = parse_qsl(parts.query, keep_blank_values=True)
    if not query:
        return value
    redacted: list[tuple[str, str]] = []
    for key, query_value in query:
        lower = key.lower()
        if any(marker in lower for marker in _REDACT_KEYS):
            redacted.append((key, "[REDACTED]"))
        else:
            redacted.append((key, query_value))
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(redacted, doseq=True),
            parts.fragment,
        )
    )
