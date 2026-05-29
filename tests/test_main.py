from __future__ import annotations

from types import SimpleNamespace

import pytest

import wordlift_sdk.main as main


def _container(result):
    class _Workflow:
        async def run(self):
            return result

    class _Container:
        async def create_kg_import_workflow(self):
            return _Workflow()

    return _Container


@pytest.mark.asyncio
async def test_run_kg_import_workflow_invokes_container_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = SimpleNamespace(url_count=1, failures=[], ok=True, elapsed_seconds=0.0)
    monkeypatch.setattr(main, "ApplicationContainer", _container(result))
    await main.run_kg_import_workflow()


@pytest.mark.asyncio
async def test_run_kg_import_workflow_raises_on_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    failures = [SimpleNamespace()]
    result = SimpleNamespace(
        url_count=3, failures=failures, ok=False, elapsed_seconds=0.0
    )
    monkeypatch.setattr(main, "ApplicationContainer", _container(result))
    with pytest.raises(SystemExit, match="Total URLs: 3, Successes: 2, Failures: 1"):
        await main.run_kg_import_workflow()
