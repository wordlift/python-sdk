from __future__ import annotations

import logging
from pathlib import Path

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
    assert "SHEETS_URL = 'https://docs.google.com/sheets/d/x'" in lines
    assert "SHEETS_NAME = 'Sheet1'" in lines
    assert "A = 1" in lines


def test_build_settings_lines_requires_source_fields() -> None:
    with pytest.raises(CloudWorkflowConfigError, match="Either urls or sheets_url"):
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
