from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Sequence


ProviderFactory = Callable[[str], Any]
ContainerFactory = Callable[[Any], Any]
ProtocolFactory = Callable[[Any], Any | Awaitable[Any]]
Reporter = Callable[[str], None]


@dataclass(frozen=True)
class CloudWorkflowConfig:
    wordlift_key: str
    sheets_service_account_json: str
    overwrite: bool = False
    concurrency: int = 4
    web_page_import_mode: str = "premium_scraper"
    web_page_import_timeout: int = 60000
    urls: Sequence[str] | None = None
    sheets_url: str | None = None
    sheets_name: str | None = None
    extra_settings: Mapping[str, Any] | None = None
    debug: bool = False
    debug_profile_name: str | None = None


class CloudWorkflowConfigError(ValueError):
    pass


def _append_py_setting(lines: list[str], key: str, value: Any) -> None:
    lines.append(f"{key} = {repr(value)}")


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
    config: CloudWorkflowConfig, service_account_path: str
) -> list[str]:
    if config.urls:
        source_lines = [f"URLS = {repr(list(config.urls))}"]
    else:
        if not config.sheets_url:
            raise CloudWorkflowConfigError(
                "Either urls or sheets_url must be provided for cloud workflow."
            )
        if not config.sheets_name:
            raise CloudWorkflowConfigError(
                "sheets_name is required when using sheets_url source."
            )
        source_lines = [
            f"SHEETS_URL = {repr(config.sheets_url)}",
            f"SHEETS_NAME = {repr(config.sheets_name)}",
        ]

    lines = [f"WORDLIFT_KEY = {repr(config.wordlift_key)}"]
    lines.extend(source_lines)
    lines.append(f"SHEETS_SERVICE_ACCOUNT = {repr(service_account_path)}")
    lines.append(f"WEB_PAGE_IMPORT_MODE = {repr(config.web_page_import_mode)}")
    lines.append(f"WEB_PAGE_IMPORT_TIMEOUT = {repr(config.web_page_import_timeout)}")
    lines.append(f"CONCURRENCY = {repr(config.concurrency)}")
    lines.append(f"OVERWRITE = {repr(config.overwrite)}")

    if config.extra_settings:
        for key, value in config.extra_settings.items():
            _append_py_setting(lines, key, value)

    return lines


async def run_cloud_workflow(
    *,
    config: CloudWorkflowConfig,
    configuration_provider_create: ProviderFactory,
    container_factory: ContainerFactory,
    protocol_factory: ProtocolFactory,
    on_info: Reporter | None = None,
) -> None:
    temp_sa_path: str | None = None
    temp_config_path: str | None = None

    try:
        debug_dir = get_debug_output_dir(config)
        if debug_dir:
            debug_dir.mkdir(parents=True, exist_ok=True)
            if on_info:
                on_info(
                    f"Debug mode enabled. Saving intermediate graphs to: {debug_dir}"
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

    finally:
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
