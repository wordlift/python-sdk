import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from rdflib import Graph, URIRef

from wordlift_sdk.protocol.entity_patch.entity_patch import EntityPatch
from wordlift_sdk.protocol.entity_patch.entity_patch_queue import EntityPatchQueue
from wordlift_sdk.protocol.graph.graph_queue import GraphQueue
from wordlift_sdk.protocol.load_override_class import load_override_class
from wordlift_sdk.render.render_options import RenderOptions
from wordlift_sdk.structured_data.agent import AgentGenerator as AgentWrapper


class _FakeApiClient:
    def __init__(self, configuration=None):
        self.configuration = configuration

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeEntitiesApi:
    def __init__(self, api_client):
        self.api_client = api_client
        self.calls = []

    async def create_or_update_entities(self, payload, _content_type=None):
        self.calls.append((payload, _content_type))

    async def patch_entities(self, id, entity_patch_request):
        self.calls.append((id, entity_patch_request))


@pytest.mark.asyncio
async def test_graph_queue_put_deduplicates(monkeypatch):
    import wordlift_sdk.protocol.graph.graph_queue as graph_queue_module

    api = _FakeEntitiesApi(None)
    monkeypatch.setattr(graph_queue_module.wordlift_client, "ApiClient", _FakeApiClient)
    monkeypatch.setattr(
        graph_queue_module.wordlift_client, "EntitiesApi", lambda client: api
    )

    queue = GraphQueue(client_configuration=SimpleNamespace())
    graph = Graph()
    graph.add((URIRef("urn:s"), URIRef("urn:p"), URIRef("urn:o")))

    await queue.put(graph)
    await queue.put(graph)

    assert len(api.calls) == 1


@pytest.mark.asyncio
async def test_graph_queue_put_reraises_create_error(monkeypatch):
    import wordlift_sdk.protocol.graph.graph_queue as graph_queue_module

    class _FailingApi(_FakeEntitiesApi):
        async def create_or_update_entities(self, payload, _content_type=None):
            raise RuntimeError("boom")

    monkeypatch.setattr(graph_queue_module.wordlift_client, "ApiClient", _FakeApiClient)
    monkeypatch.setattr(
        graph_queue_module.wordlift_client,
        "EntitiesApi",
        lambda client: _FailingApi(client),
    )

    queue = GraphQueue(client_configuration=SimpleNamespace())
    graph = Graph()
    graph.add((URIRef("urn:s"), URIRef("urn:p"), URIRef("urn:o")))

    with pytest.raises(RuntimeError, match="boom"):
        await queue.put(graph)


def test_graph_queue_hash_graph_is_stable():
    graph1 = Graph()
    graph2 = Graph()
    triple = (URIRef("urn:s"), URIRef("urn:p"), URIRef("urn:o"))
    graph1.add(triple)
    graph2.add(triple)

    assert GraphQueue.hash_graph(graph1) == GraphQueue.hash_graph(graph2)


@pytest.mark.asyncio
async def test_entity_patch_queue_put(monkeypatch):
    import wordlift_sdk.protocol.entity_patch.entity_patch_queue as patch_queue_module

    api = _FakeEntitiesApi(None)
    monkeypatch.setattr(patch_queue_module.wordlift_client, "ApiClient", _FakeApiClient)
    monkeypatch.setattr(
        patch_queue_module.wordlift_client, "EntitiesApi", lambda client: api
    )

    queue = EntityPatchQueue(client_configuration=SimpleNamespace())
    patch = EntityPatch(iri="urn:entity", requests=[])
    await queue.put(patch)

    assert api.calls == [("urn:entity", [])]


@pytest.mark.asyncio
async def test_entity_patch_queue_reraises_errors(monkeypatch):
    import wordlift_sdk.protocol.entity_patch.entity_patch_queue as patch_queue_module

    class _FailingApi(_FakeEntitiesApi):
        async def patch_entities(self, id, entity_patch_request):
            raise RuntimeError("patch-failed")

    monkeypatch.setattr(patch_queue_module.wordlift_client, "ApiClient", _FakeApiClient)
    monkeypatch.setattr(
        patch_queue_module.wordlift_client,
        "EntitiesApi",
        lambda client: _FailingApi(client),
    )

    queue = EntityPatchQueue(client_configuration=SimpleNamespace())
    patch = EntityPatch(iri="urn:entity", requests=[])

    with pytest.raises(RuntimeError, match="patch-failed"):
        await queue.put(patch)


def test_load_override_class_uses_default_and_override(tmp_path: Path, monkeypatch):
    class DefaultClass:
        def __init__(self, value):
            self.value = value

    instance = load_override_class("missing", "Override", DefaultClass, value=1)
    assert isinstance(instance, DefaultClass)
    assert instance.value == 1

    override_dir = tmp_path / "overrides"
    override_dir.mkdir()
    (override_dir / "demo.py").write_text(
        "class Override:\n    def __init__(self, value):\n        self.value = value\n"
    )
    monkeypatch.setenv("WORDLIFT_OVERRIDE_DIR", str(override_dir))

    overridden = load_override_class("demo", "Override", DefaultClass, value=9)
    assert overridden.__class__.__name__ == "Override"
    assert overridden.value == 9
    assert str(override_dir.resolve()) in sys.path


def test_html_renderer_render_and_helpers(monkeypatch):
    import wordlift_sdk.render.html_renderer as html_renderer_module

    class _Page:
        def __init__(self):
            self.closed = False
            self.wait_calls = []
            self.calls = 0

        def content(self):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("not-ready")
            return "<html>ok</html>"

        def wait_for_load_state(self, state, timeout):
            self.wait_calls.append((state, timeout))

        def close(self):
            self.closed = True

    class _Response:
        @property
        def status(self):
            raise RuntimeError("status unavailable")

    page = _Page()

    class _Browser:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def open(self, url):
            return page, _Response(), 0, [{"url": url}]

    monkeypatch.setattr(html_renderer_module, "Browser", _Browser)
    monkeypatch.setattr(
        html_renderer_module,
        "HtmlConverter",
        lambda: SimpleNamespace(convert=lambda html: "<xhtml/>"),
    )

    renderer = html_renderer_module.HtmlRenderer()
    options = RenderOptions(
        url="http://localhost:8080", timeout_ms=100, wait_until="load"
    )
    rendered = renderer.render(options)

    assert rendered.html == "<html>ok</html>"
    assert rendered.xhtml == "<xhtml/>"
    assert rendered.status_code is None
    assert page.closed is True
    assert renderer._is_localhost_url("http://api.localhost/path") is True
    assert renderer._is_localhost_url("https://example.org") is False


def test_html_renderer_raises_when_page_missing(monkeypatch):
    import wordlift_sdk.render.html_renderer as html_renderer_module

    class _Browser:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def open(self, url):
            return None, None, 0, []

    monkeypatch.setattr(html_renderer_module, "Browser", _Browser)

    renderer = html_renderer_module.HtmlRenderer()
    with pytest.raises(RuntimeError, match="Failed to open page"):
        renderer.render(
            RenderOptions(url="https://example.org", timeout_ms=50, wait_until="load")
        )


def test_agent_wrappers_delegate(monkeypatch, tmp_path: Path):
    import wordlift_sdk.structured_data.agent_generator as agent_generator_module

    called = {}

    def _generate_from_agent(*args, **kwargs):
        called["args"] = args
        called["kwargs"] = kwargs
        return "y", {"@id": "x"}

    monkeypatch.setattr(
        "wordlift_sdk.structured_data.agent_generator.generate_from_agent",
        _generate_from_agent,
    )

    engine = agent_generator_module.AgentGenerator()
    y, j = engine.generate_from_agent("a", foo=1)
    assert y == "y"
    assert j == {"@id": "x"}

    class _Engine:
        def generate_from_agent(self, *args, **kwargs):
            return "mapped", {"ok": True}

    wrapper = AgentWrapper(engine=_Engine())
    yarrml, jsonld = wrapper.generate(
        "https://example.org",
        "<html></html>",
        "<html/>",
        "clean",
        "k",
        "https://dataset",
        "Article",
        tmp_path,
        debug=False,
        max_retries=1,
        max_nesting_depth=2,
        quality_check=False,
    )
    assert yarrml == "mapped"
    assert jsonld == {"ok": True}
