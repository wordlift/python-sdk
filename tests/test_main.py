from __future__ import annotations

import pytest

import wordlift_sdk.main as main


@pytest.mark.asyncio
async def test_run_kg_import_workflow_invokes_container_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, bool] = {"ran": False}

    class _Workflow:
        async def run(self) -> None:
            calls["ran"] = True

    class _Container:
        async def create_kg_import_workflow(self):
            return _Workflow()

    monkeypatch.setattr(main, "ApplicationContainer", _Container)
    await main.run_kg_import_workflow()
    assert calls["ran"] is True
