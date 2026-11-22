from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from wordlift_sdk.url_source.url_source import Url, UrlSource
from wordlift_sdk.workflow.kg_import_workflow import KgImportWorkflow
from wordlift_sdk.workflow.url_handler.default_url_handler import DefaultUrlHandler
from wordlift_sdk.workflow.url_handler.url_handler import UrlHandler


class _ListUrlSource(UrlSource):
    def __init__(self, urls: list[Url]) -> None:
        self._urls = urls

    async def urls(self):
        for url in self._urls:
            yield url


class _OkHandler(UrlHandler):
    async def __call__(self, url: Url):
        return None


class _FailingHandler(UrlHandler):
    async def __call__(self, url: Url):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_kg_import_workflow_fails_after_urls_when_handlers_error(monkeypatch):
    async def _noop_graphs(self):
        return None

    monkeypatch.setattr(
        "wordlift_sdk.workflow.kg_import_workflow.TtlLiquidGraphFactory.graphs",
        _noop_graphs,
    )

    url_source = _ListUrlSource([Url(value="https://example.com/a")])
    handler = DefaultUrlHandler([_OkHandler(), _FailingHandler()])
    workflow = KgImportWorkflow(
        context=SimpleNamespace(),
        url_source=url_source,
        url_handler=handler,
        concurrency=1,
    )

    result = await workflow.run()

    assert result.failures
    failure = result.failures[0]
    assert failure.url.value == "https://example.com/a"
    assert failure.handler_name == "_FailingHandler"
    assert "boom" in failure.message
    assert failure.timestamp.tzinfo is not None


@pytest.mark.asyncio
async def test_kg_import_workflow_fails_when_liquid_template_write_fails(
    monkeypatch, tmp_path
):
    templates = tmp_path / "data" / "templates"
    templates.mkdir(parents=True)
    (templates / "org.ttl.liquid").write_text(
        "<https://data.example.com/org> a <https://schema.org/Organization> ."
    )
    monkeypatch.chdir(tmp_path)

    context = SimpleNamespace(
        account=SimpleNamespace(),
        graph_queue=SimpleNamespace(put=AsyncMock(side_effect=RuntimeError("500"))),
    )
    workflow = KgImportWorkflow(
        context=context,
        url_source=_ListUrlSource([]),
        url_handler=DefaultUrlHandler([_OkHandler()]),
        concurrency=1,
    )

    with pytest.raises(RuntimeError, match="500"):
        await workflow.run()
