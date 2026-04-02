from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime
from inspect import isawaitable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Sequence

from wordlift_sdk.render.render_options import (
    DEFAULT_PLAYWRIGHT_TIMEOUT_MS,
    DEFAULT_PLAYWRIGHT_WAIT_UNTIL,
)


ProviderFactory = Callable[[str], Any]
ContainerFactory = Callable[[Any], Any]
ProtocolFactory = Callable[[Any], Any | Awaitable[Any]]
Reporter = Callable[[str], None]
KpiReporter = Callable[[dict[str, Any]], None]
ProgressReporter = Callable[[dict[str, Any]], None]

logger = logging.getLogger(__name__)


def _format_failure_timestamp(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw)
        text = dt.strftime("%b %d, %H:%M:%S")
        return text.replace(" 0", " ")
    except Exception:
        return raw


@dataclass(frozen=True)
class CloudWorkflowConfig:
    wordlift_key: str
    graph_write_strategy: str = "patch"
    sheets_service_account_json: str | None = None
    overwrite: bool = False
    concurrency: int = 4
    ingest_loader: str = "web_scrape_api"
    ingest_timeout_ms: int | None = None
    playwright_wait_until: str | None = None
    urls: Sequence[str] | None = None
    sitemap_url: str | None = None
    sitemap_url_pattern: str | None = None
    sheets_url: str | None = None
    sheets_name: str | None = None
    extra_settings: Mapping[str, Any] | None = None
    debug: bool = False
    debug_profile_name: str | None = None


class CloudWorkflowConfigError(ValueError):
    pass


def _append_py_setting(lines: list[str], key: str, value: Any) -> None:
    lines.append(f"{key} = {repr(value)}")


def _extra_setting(
    extra_settings: Mapping[str, Any] | None,
    *keys: str,
) -> Any | None:
    if not extra_settings:
        return None
    for key in keys:
        if key in extra_settings:
            return extra_settings[key]
    return None


def _resolved_ingest_timeout_ms(config: CloudWorkflowConfig) -> int:
    # Prefer the typed modern field, then modern/legacy compatibility keys, then SDK defaults.
    if config.ingest_timeout_ms is not None:
        return config.ingest_timeout_ms
    value = _extra_setting(
        config.extra_settings,
        "INGEST_TIMEOUT_MS",
        "ingest_timeout_ms",
        "WEB_PAGE_IMPORT_TIMEOUT",
        "web_page_import_timeout",
    )
    if value is None:
        return DEFAULT_PLAYWRIGHT_TIMEOUT_MS
    return int(value)


def _resolved_playwright_wait_until(config: CloudWorkflowConfig) -> str:
    # Prefer the typed field and only fall back to generic extra settings for compatibility.
    if config.playwright_wait_until is not None:
        return config.playwright_wait_until
    value = _extra_setting(
        config.extra_settings,
        "PLAYWRIGHT_WAIT_UNTIL",
        "playwright_wait_until",
    )
    if value is None:
        return DEFAULT_PLAYWRIGHT_WAIT_UNTIL
    return str(value)


def get_debug_output_dir(
    config: CloudWorkflowConfig, root_dir: Path | None = None
) -> Path | None:
    if not config.debug:
        return None
    if not config.debug_profile_name:
        raise CloudWorkflowConfigError(
            "debug_profile_name is required when debug is enabled."
        )
    base = root_dir or Path.cwd()
    return base / "output" / "debug_cloud" / config.debug_profile_name


def _build_settings_lines(
    config: CloudWorkflowConfig, service_account_path: str | None
) -> list[str]:
    if config.sitemap_url_pattern and not config.sitemap_url:
        raise CloudWorkflowConfigError(
            "sitemap_url_pattern requires sitemap_url source."
        )

    source_kinds: list[str] = []
    if config.urls:
        source_kinds.append("urls")
    if config.sitemap_url:
        source_kinds.append("sitemap")
    if config.sheets_url:
        source_kinds.append("sheets")

    if len(source_kinds) == 0:
        raise CloudWorkflowConfigError(
            "Exactly one source is required: urls, sitemap_url, or sheets_url."
        )
    if len(source_kinds) > 1:
        raise CloudWorkflowConfigError(
            "Exactly one source is allowed: urls, sitemap_url, or sheets_url."
        )

    if source_kinds[0] == "urls":
        source_lines = [
            "INGEST_SOURCE = 'urls'",
            f"URLS = {repr(list(config.urls or []))}",
        ]
    elif source_kinds[0] == "sitemap":
        source_lines = [
            "INGEST_SOURCE = 'sitemap'",
            f"SITEMAP_URL = {repr(config.sitemap_url)}",
        ]
        if config.sitemap_url_pattern:
            source_lines.append(
                f"SITEMAP_URL_PATTERN = {repr(config.sitemap_url_pattern)}"
            )
    else:
        if not service_account_path:
            raise CloudWorkflowConfigError(
                "sheets_service_account_json is required when using sheets_url source."
            )
        if not config.sheets_name:
            raise CloudWorkflowConfigError(
                "sheets_name is required when using sheets_url source."
            )
        source_lines = [
            "INGEST_SOURCE = 'sheets'",
            f"SHEETS_URL = {repr(config.sheets_url)}",
            f"SHEETS_NAME = {repr(config.sheets_name)}",
            f"SHEETS_SERVICE_ACCOUNT = {repr(service_account_path)}",
        ]

    lines = [f"WORDLIFT_KEY = {repr(config.wordlift_key)}"]
    lines.extend(source_lines)
    lines.append(f"INGEST_LOADER = {repr(config.ingest_loader)}")
    lines.append(f"INGEST_TIMEOUT_MS = {repr(_resolved_ingest_timeout_ms(config))}")
    lines.append(
        f"PLAYWRIGHT_WAIT_UNTIL = {repr(_resolved_playwright_wait_until(config))}"
    )
    lines.append(f"CONCURRENCY = {repr(config.concurrency)}")
    lines.append(f"OVERWRITE = {repr(config.overwrite)}")

    if config.extra_settings:
        for key, value in config.extra_settings.items():
            if key in {
                "INGEST_TIMEOUT_MS",
                "ingest_timeout_ms",
                "WEB_PAGE_IMPORT_TIMEOUT",
                "web_page_import_timeout",
                "PLAYWRIGHT_WAIT_UNTIL",
                "playwright_wait_until",
            }:
                continue
            _append_py_setting(lines, key, value)

    return lines


async def run_cloud_workflow(
    *,
    config: CloudWorkflowConfig,
    configuration_provider_create: ProviderFactory,
    container_factory: ContainerFactory,
    protocol_factory: ProtocolFactory,
    on_info: Reporter | None = None,
    on_kpi: KpiReporter | None = None,
    on_progress: ProgressReporter | None = None,
) -> None:
    temp_sa_path: str | None = None
    temp_config_path: str | None = None
    protocol = None

    try:
        debug_dir = get_debug_output_dir(config)
        if debug_dir:
            debug_dir.mkdir(parents=True, exist_ok=True)
            if on_info:
                on_info(
                    f"Debug mode enabled. Saving intermediate graphs to: {debug_dir}"
                )

        if config.sheets_url:
            if not config.sheets_service_account_json:
                raise CloudWorkflowConfigError(
                    "sheets_service_account_json is required when using sheets_url source."
                )
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as f_sa:
                f_sa.write(config.sheets_service_account_json)
                temp_sa_path = f_sa.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f_cfg:
            settings = _build_settings_lines(config, temp_sa_path)
            f_cfg.write("\n".join(settings) + "\n")
            temp_config_path = f_cfg.name

        if on_info:
            on_info(f"Initializing SDK with dynamic config: {temp_config_path}")

        provider = configuration_provider_create(temp_config_path)
        container = container_factory(provider)
        context = await container.get_context()

        try:
            protocol = protocol_factory(
                context,
                debug_dir=debug_dir,
                workflow_config=config,
                on_progress=on_progress,
                graph_write_strategy=config.graph_write_strategy,
            )
        except TypeError:
            protocol = protocol_factory(context)
        if hasattr(protocol, "__await__"):
            protocol = await protocol

        container.set_protocol(protocol)

        if on_info:
            on_info("Creating Cloud Import Workflow...")

        workflow = await container.create_kg_import_workflow()

        if on_info:
            on_info("Running Workflow (this may take several minutes)...")

        await workflow.run()

        url_handler = getattr(workflow, "_url_handler", None)
        failures = getattr(url_handler, "failures", None) if url_handler else None
        if isinstance(failures, list) and failures:
            total_urls = getattr(workflow, "_url_count", None)
            if isinstance(total_urls, int) and total_urls >= 0:
                success_count = max(total_urls - len(failures), 0)
                summary_lines = [
                    f"Total URLs: {total_urls}",
                    f"Successes: {success_count}",
                    f"Failures: {len(failures)}",
                ]
            else:
                summary_lines = [f"{len(failures)} URL handler failure(s) detected."]
            for _, url, handler_name, message in failures[:10]:
                summary_lines.append(f"- {handler_name} failed for {url}: {message}")
            if len(failures) > 10:
                summary_lines.append(f"- ... and {len(failures) - 10} more.")
            summary = "\n".join(summary_lines)
            logger.error(summary)

            report_path = Path.cwd() / "output" / "graph_sync_failures.md"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_lines = [
                "# Graph Sync Failures",
                "",
                f"Total failures: **{len(failures)}**",
                f"Total URLs: **{total_urls}**" if isinstance(total_urls, int) else "",
                f"Successes: **{success_count}**"
                if isinstance(total_urls, int)
                else "",
                "",
                "## Details",
                "",
                "| Timestamp (UTC) | URL | Handler | Error |",
                "| --- | --- | --- | --- |",
            ]
            for timestamp, url, handler_name, message in failures:
                safe_message = str(message).replace("\n", " ").replace("|", "\\|")
                url_value = getattr(url, "value", None)
                display_url = str(url_value or url)
                display_ts = _format_failure_timestamp(timestamp)
                report_lines.append(
                    f"| {display_ts} | `{display_url}` | `{handler_name}` | `{safe_message}` |"
                )
            report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
            logger.error("Wrote failure report to %s", report_path)

            raise SystemExit(summary)

    finally:
        if protocol is not None and on_kpi is not None:
            get_kpi_summary = getattr(protocol, "get_kpi_summary", None)
            if callable(get_kpi_summary):
                try:
                    on_kpi(get_kpi_summary())
                except Exception:
                    logger.warning(
                        "Failed to emit kg_build KPI summary via on_kpi callback.",
                        exc_info=True,
                    )
        if protocol is not None:
            close = getattr(protocol, "close", None)
            if callable(close):
                result = close()
                if isawaitable(result):
                    await result
        if temp_config_path and os.path.exists(temp_config_path):
            os.remove(temp_config_path)
        if temp_sa_path and os.path.exists(temp_sa_path):
            os.remove(temp_sa_path)


__all__ = [
    "CloudWorkflowConfig",
    "CloudWorkflowConfigError",
    "get_debug_output_dir",
    "run_cloud_workflow",
]
