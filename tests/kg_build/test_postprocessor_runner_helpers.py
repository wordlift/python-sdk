from __future__ import annotations

from types import ModuleType

from rdflib import Graph, Literal, URIRef

from wordlift_sdk.kg_build.postprocessors import oneshot as runner


def test_load_class_variants(monkeypatch) -> None:
    mod = ModuleType("m")

    class Demo:
        pass

    mod.Demo = Demo
    monkeypatch.setattr(runner.importlib, "import_module", lambda _name: mod)
    assert runner._load_class("m:Demo") is Demo

    try:
        runner._load_class("invalid")
        assert False
    except ValueError:
        pass

    try:
        runner._load_class("m:Missing")
        assert False
    except AttributeError:
        pass


def test_read_write_graph_nquads_roundtrip(tmp_path) -> None:
    g = Graph()
    g.add(
        (URIRef("https://example.com/s"), URIRef("https://example.com/p"), Literal("v"))
    )
    path = tmp_path / "g.nq"
    runner._write_graph_nquads(g, path)
    out = runner._read_graph_nquads(path)
    assert len(out) == 1
