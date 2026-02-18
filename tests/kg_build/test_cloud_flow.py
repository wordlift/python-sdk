from __future__ import annotations

import pytest

from wordlift_sdk.kg_build.cloud_flow import CloudWorkflowConfig, run_cloud_workflow


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
async def test_cloud_flow_closes_protocol_on_failure() -> None:
    protocol = _Protocol()

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
        )

    assert protocol.closed is True
