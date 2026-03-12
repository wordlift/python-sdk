from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from wordlift_sdk.kg_build.cloud_flow import (
    CloudWorkflowConfig,
    CloudWorkflowConfigError,
    _build_settings_lines,
    get_debug_output_dir,
    run_cloud_workflow,
)


class _Workflow:
    async def run(self) -> None:
        return None


class _FailingWorkflow:
    async def run(self) -> None:
        raise RuntimeError("workflow failed")


class _Container:
    def __init__(self, workflow):
        self._workflow = workflow
        self.protocol = None

    async def get_context(self):
        return object()

    def set_protocol(self, protocol):
        self.protocol = protocol

    async def create_kg_import_workflow(self):
        return self._workflow


class _Protocol:
    def __init__(self):
        self.closed = False
        self.progress_cb = None

    def close(self):
        self.closed = True

    def get_kpi_summary(self):
        return {"totals": {"total_entities": 1}}


class _AwaitableProtocol:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True

    def get_kpi_summary(self):
        return {"totals": {"total_entities": 2}}


class _AsyncCloseProtocol(_AwaitableProtocol):
    def close(self):
        async def _close():
            self.closed = True

        return _close()


@pytest.mark.asyncio
async def test_cloud_flow_closes_protocol_on_success() -> None:
    protocol = _Protocol()

    await run_cloud_workflow(
        config=CloudWorkflowConfig(
            wordlift_key="key",
            sheets_service_account_json="{}",
            urls=["https://example.com"],
        ),
        configuration_provider_create=lambda _: object(),
        container_factory=lambda _: _Container(_Workflow()),
        protocol_factory=lambda *_args, **_kwargs: protocol,
    )

    assert protocol.closed is True


@pytest.mark.asyncio
async def test_cloud_flow_emits_kpi_summary_when_callback_provided() -> None:
    protocol = _Protocol()
    captured: list[dict[str, object]] = []

    await run_cloud_workflow(
        config=CloudWorkflowConfig(
            wordlift_key="key",
            sheets_service_account_json="{}",
            urls=["https://example.com"],
        ),
        configuration_provider_create=lambda _: object(),
        container_factory=lambda _: _Container(_Workflow()),
        protocol_factory=lambda *_args, **_kwargs: protocol,
        on_kpi=lambda payload: captured.append(payload),
    )

    assert captured == [{"totals": {"total_entities": 1}}]


@pytest.mark.asyncio
async def test_cloud_flow_closes_protocol_on_failure() -> None:
    protocol = _Protocol()
    captured: list[dict[str, object]] = []

    with pytest.raises(RuntimeError, match="workflow failed"):
        await run_cloud_workflow(
            config=CloudWorkflowConfig(
                wordlift_key="key",
                sheets_service_account_json="{}",
                urls=["https://example.com"],
            ),
            configuration_provider_create=lambda _: object(),
            container_factory=lambda _: _Container(_FailingWorkflow()),
            protocol_factory=lambda *_args, **_kwargs: protocol,
            on_kpi=lambda payload: captured.append(payload),
        )

    assert protocol.closed is True
    assert captured == [{"totals": {"total_entities": 1}}]


def test_get_debug_output_dir_requires_profile_name() -> None:
    with pytest.raises(
        CloudWorkflowConfigError, match="debug_profile_name is required"
    ):
        get_debug_output_dir(
            CloudWorkflowConfig(
                wordlift_key="k",
                sheets_service_account_json="{}",
                urls=["https://example.com"],
                debug=True,
            )
        )


def test_get_debug_output_dir_returns_expected_path(tmp_path: Path) -> None:
    out = get_debug_output_dir(
        CloudWorkflowConfig(
            wordlift_key="k",
            sheets_service_account_json="{}",
            urls=["https://example.com"],
            debug=True,
            debug_profile_name="profile-a",
        ),
        root_dir=tmp_path,
    )
    assert out == tmp_path / "output" / "debug_cloud" / "profile-a"


def test_build_settings_lines_with_sheets_and_extra_settings() -> None:
    config = CloudWorkflowConfig(
        wordlift_key="k",
        sheets_service_account_json="{}",
        sheets_url="https://docs.google.com/sheets/d/x",
        sheets_name="Sheet1",
        extra_settings={"A": 1},
    )
    lines = _build_settings_lines(config, "/tmp/sa.json")
    assert "INGEST_SOURCE = 'sheets'" in lines
    assert "SHEETS_URL = 'https://docs.google.com/sheets/d/x'" in lines
    assert "SHEETS_NAME = 'Sheet1'" in lines
    assert "INGEST_LOADER = 'web_scrape_api'" in lines
    assert "INGEST_TIMEOUT_MS = 30000" in lines
    assert "PLAYWRIGHT_WAIT_UNTIL = 'domcontentloaded'" in lines
    assert "A = 1" in lines


def test_build_settings_lines_with_sitemap_and_pattern() -> None:
    config = CloudWorkflowConfig(
        wordlift_key="k",
        sheets_service_account_json="{}",
        sitemap_url="https://example.com/sitemap.xml",
        sitemap_url_pattern=r"^https://example.com/blog/",
    )
    lines = _build_settings_lines(config, "/tmp/sa.json")
    assert "INGEST_SOURCE = 'sitemap'" in lines
    assert "SITEMAP_URL = 'https://example.com/sitemap.xml'" in lines
    assert "SITEMAP_URL_PATTERN = '^https://example.com/blog/'" in lines


def test_build_settings_lines_uses_typed_playwright_wait_until_and_timeout_override() -> (
    None
):
    lines = _build_settings_lines(
        CloudWorkflowConfig(
            wordlift_key="k",
            sheets_service_account_json="{}",
            urls=["https://example.com"],
            ingest_timeout_ms=45000,
            playwright_wait_until="networkidle",
        ),
        "/tmp/sa.json",
    )
    assert "INGEST_TIMEOUT_MS = 45000" in lines
    assert "PLAYWRIGHT_WAIT_UNTIL = 'networkidle'" in lines


def test_build_settings_lines_prefers_modern_timeout_over_legacy_alias() -> None:
    lines = _build_settings_lines(
        CloudWorkflowConfig(
            wordlift_key="k",
            sheets_service_account_json="{}",
            urls=["https://example.com"],
            ingest_timeout_ms=12000,
            extra_settings={
                "WEB_PAGE_IMPORT_TIMEOUT": 9000,
                "INGEST_TIMEOUT_MS": 8000,
            },
        ),
        "/tmp/sa.json",
    )
    assert "INGEST_TIMEOUT_MS = 12000" in lines
    assert "WEB_PAGE_IMPORT_TIMEOUT = 9000" not in lines


def test_build_settings_lines_uses_legacy_timeout_alias_only_as_fallback() -> None:
    lines = _build_settings_lines(
        CloudWorkflowConfig(
            wordlift_key="k",
            sheets_service_account_json="{}",
            urls=["https://example.com"],
            extra_settings={"web_page_import_timeout": 15000},
        ),
        "/tmp/sa.json",
    )
    assert "INGEST_TIMEOUT_MS = 15000" in lines
    assert "web_page_import_timeout = 15000" not in lines


def test_build_settings_lines_prefers_typed_wait_until_over_extra_settings() -> None:
    lines = _build_settings_lines(
        CloudWorkflowConfig(
            wordlift_key="k",
            sheets_service_account_json="{}",
            urls=["https://example.com"],
            playwright_wait_until="commit",
            extra_settings={"PLAYWRIGHT_WAIT_UNTIL": "load"},
        ),
        "/tmp/sa.json",
    )
    assert "PLAYWRIGHT_WAIT_UNTIL = 'commit'" in lines


def test_build_settings_lines_requires_source_fields() -> None:
    with pytest.raises(
        CloudWorkflowConfigError, match="Exactly one source is required"
    ):
        _build_settings_lines(
            CloudWorkflowConfig(wordlift_key="k", sheets_service_account_json="{}"),
            "/tmp/sa.json",
        )

    with pytest.raises(CloudWorkflowConfigError, match="sheets_name is required"):
        _build_settings_lines(
            CloudWorkflowConfig(
                wordlift_key="k",
                sheets_service_account_json="{}",
                sheets_url="https://docs.google.com/sheets/d/x",
            ),
            "/tmp/sa.json",
        )

    with pytest.raises(
        CloudWorkflowConfigError, match="sheets_service_account_json is required"
    ):
        _build_settings_lines(
            CloudWorkflowConfig(
                wordlift_key="k",
                sheets_service_account_json=None,
                sheets_url="https://docs.google.com/sheets/d/x",
                sheets_name="Sheet1",
            ),
            None,
        )


def test_build_settings_lines_rejects_multiple_sources() -> None:
    with pytest.raises(CloudWorkflowConfigError, match="Exactly one source is allowed"):
        _build_settings_lines(
            CloudWorkflowConfig(
                wordlift_key="k",
                sheets_service_account_json="{}",
                urls=["https://example.com"],
                sitemap_url="https://example.com/sitemap.xml",
            ),
            "/tmp/sa.json",
        )


def test_build_settings_lines_requires_sitemap_url_for_pattern() -> None:
    with pytest.raises(
        CloudWorkflowConfigError, match="sitemap_url_pattern requires sitemap_url"
    ):
        _build_settings_lines(
            CloudWorkflowConfig(
                wordlift_key="k",
                sheets_service_account_json="{}",
                urls=["https://example.com"],
                sitemap_url_pattern=r"^https://example.com/",
            ),
            "/tmp/sa.json",
        )


@pytest.mark.asyncio
async def test_cloud_flow_uses_typeerror_fallback_and_awaitable_protocol() -> None:
    protocol = _AwaitableProtocol()
    captured: list[dict[str, object]] = []

    async def protocol_factory(_context):
        return protocol

    await run_cloud_workflow(
        config=CloudWorkflowConfig(
            wordlift_key="key",
            sheets_service_account_json="{}",
            urls=["https://example.com"],
        ),
        configuration_provider_create=lambda _: object(),
        container_factory=lambda _: _Container(_Workflow()),
        protocol_factory=protocol_factory,
        on_kpi=lambda payload: captured.append(payload),
    )

    assert protocol.closed is True
    assert captured == [{"totals": {"total_entities": 2}}]


@pytest.mark.asyncio
async def test_cloud_flow_logs_warning_when_on_kpi_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    protocol = _Protocol()

    with caplog.at_level(logging.WARNING):
        await run_cloud_workflow(
            config=CloudWorkflowConfig(
                wordlift_key="key",
                sheets_service_account_json="{}",
                urls=["https://example.com"],
            ),
            configuration_provider_create=lambda _: object(),
            container_factory=lambda _: _Container(_Workflow()),
            protocol_factory=lambda *_args, **_kwargs: protocol,
            on_kpi=lambda _payload: (_ for _ in ()).throw(RuntimeError("kpi boom")),
        )

    assert "Failed to emit kg_build KPI summary via on_kpi callback." in caplog.text


@pytest.mark.asyncio
async def test_cloud_flow_passes_on_progress_to_protocol_factory() -> None:
    protocol = _Protocol()
    captured_kwargs: dict[str, object] = {}

    def protocol_factory(*args, **kwargs):
        del args
        captured_kwargs.update(kwargs)
        return protocol

    progress_events: list[dict[str, object]] = []
    await run_cloud_workflow(
        config=CloudWorkflowConfig(
            wordlift_key="key",
            sheets_service_account_json="{}",
            urls=["https://example.com"],
        ),
        configuration_provider_create=lambda _: object(),
        container_factory=lambda _: _Container(_Workflow()),
        protocol_factory=protocol_factory,
        on_progress=lambda payload: progress_events.append(payload),
    )

    assert "on_progress" in captured_kwargs
    assert callable(captured_kwargs["on_progress"])


@pytest.mark.asyncio
async def test_cloud_flow_passes_graph_write_strategy_to_protocol_factory() -> None:
    protocol = _Protocol()
    captured_kwargs: dict[str, object] = {}

    def protocol_factory(*args, **kwargs):
        del args
        captured_kwargs.update(kwargs)
        return protocol

    await run_cloud_workflow(
        config=CloudWorkflowConfig(
            wordlift_key="key",
            sheets_service_account_json="{}",
            urls=["https://example.com"],
            graph_write_strategy="put",
        ),
        configuration_provider_create=lambda _: object(),
        container_factory=lambda _: _Container(_Workflow()),
        protocol_factory=protocol_factory,
    )

    assert captured_kwargs["graph_write_strategy"] == "put"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config", "expected_source_lines"),
    [
        (
            CloudWorkflowConfig(
                wordlift_key="key",
                sheets_service_account_json="{}",
                urls=["https://example.com/a"],
            ),
            ["INGEST_SOURCE = 'urls'", "URLS = ['https://example.com/a']"],
        ),
        (
            CloudWorkflowConfig(
                wordlift_key="key",
                sheets_service_account_json="{}",
                sitemap_url="https://example.com/sitemap.xml",
                sitemap_url_pattern=r"^https://example.com/articles/",
            ),
            [
                "INGEST_SOURCE = 'sitemap'",
                "SITEMAP_URL = 'https://example.com/sitemap.xml'",
                "SITEMAP_URL_PATTERN = '^https://example.com/articles/'",
            ],
        ),
        (
            CloudWorkflowConfig(
                wordlift_key="key",
                sheets_service_account_json="{}",
                sheets_url="https://docs.google.com/sheets/d/x",
                sheets_name="Sheet1",
            ),
            [
                "INGEST_SOURCE = 'sheets'",
                "SHEETS_URL = 'https://docs.google.com/sheets/d/x'",
                "SHEETS_NAME = 'Sheet1'",
            ],
        ),
    ],
)
async def test_cloud_flow_canonical_path_source_mode_conformance(
    config: CloudWorkflowConfig,
    expected_source_lines: list[str],
) -> None:
    protocol = _Protocol()
    captured_config_lines: list[str] = []
    info_events: list[str] = []
    kpi_events: list[dict[str, object]] = []
    protocol_factory_kwargs: dict[str, Any] = {}

    def configuration_provider_create(path: str):
        captured_config_lines.extend(
            Path(path).read_text(encoding="utf-8").splitlines()
        )
        return object()

    def protocol_factory(*args, **kwargs):
        del args
        protocol_factory_kwargs.update(kwargs)
        protocol.progress_cb = kwargs.get("on_progress")
        return protocol

    await run_cloud_workflow(
        config=config,
        configuration_provider_create=configuration_provider_create,
        container_factory=lambda _: _Container(_Workflow()),
        protocol_factory=protocol_factory,
        on_info=lambda message: info_events.append(message),
        on_progress=lambda payload: None,
        on_kpi=lambda payload: kpi_events.append(payload),
    )

    for expected_line in expected_source_lines:
        assert expected_line in captured_config_lines
    assert "INGEST_LOADER = 'web_scrape_api'" in captured_config_lines
    assert "INGEST_TIMEOUT_MS = 30000" in captured_config_lines
    assert "PLAYWRIGHT_WAIT_UNTIL = 'domcontentloaded'" in captured_config_lines
    assert any("Initializing SDK with dynamic config" in msg for msg in info_events)
    assert any("Creating Cloud Import Workflow..." in msg for msg in info_events)
    assert any(
        "Running Workflow (this may take several minutes)..." in msg
        for msg in info_events
    )
    assert kpi_events == [{"totals": {"total_entities": 1}}]
    assert "on_progress" in protocol_factory_kwargs
    assert callable(protocol_factory_kwargs["on_progress"])


@pytest.mark.asyncio
async def test_cloud_flow_debug_info_and_async_close(tmp_path: Path) -> None:
    protocol = _AsyncCloseProtocol()
    info: list[str] = []

    await run_cloud_workflow(
        config=CloudWorkflowConfig(
            wordlift_key="key",
            sheets_service_account_json="{}",
            urls=["https://example.com"],
            debug=True,
            debug_profile_name="dbg",
        ),
        configuration_provider_create=lambda _: object(),
        container_factory=lambda _: _Container(_Workflow()),
        protocol_factory=lambda *_args, **_kwargs: protocol,
        on_info=lambda msg: info.append(msg),
    )

    assert protocol.closed is True
    assert any(
        "Debug mode enabled. Saving intermediate graphs to:" in msg for msg in info
    )


@pytest.mark.asyncio
async def test_cloud_flow_sheets_requires_service_account_in_run() -> None:
    with pytest.raises(
        CloudWorkflowConfigError, match="sheets_service_account_json is required"
    ):
        await run_cloud_workflow(
            config=CloudWorkflowConfig(
                wordlift_key="key",
                sheets_service_account_json=None,
                sheets_url="https://docs.google.com/sheets/d/x",
                sheets_name="Sheet1",
            ),
            configuration_provider_create=lambda _: object(),
            container_factory=lambda _: _Container(_Workflow()),
            protocol_factory=lambda *_args, **_kwargs: _Protocol(),
        )
