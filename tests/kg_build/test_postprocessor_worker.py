from __future__ import annotations

import io
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

from rdflib import Graph, Literal, URIRef

from wordlift_sdk.kg_build.postprocessors import persistent as worker


def _graph() -> Graph:
    g = Graph()
    g.add(
        (URIRef("https://example.com/s"), URIRef("https://example.com/p"), Literal("v"))
    )
    return g


def test_load_class_success_and_errors(monkeypatch) -> None:
    mod = ModuleType("m")

    class Demo:
        pass

    mod.Demo = Demo
    monkeypatch.setattr(worker.importlib, "import_module", lambda _: mod)
    assert worker._load_class("m:Demo") is Demo

    try:
        worker._load_class("invalid")
        assert False
    except ValueError:
        pass

    try:
        worker._load_class("m:Missing")
        assert False
    except AttributeError:
        pass


def test_read_and_write_graph_nquads(tmp_path: Path) -> None:
    input_path = tmp_path / "in.nq"
    out_path = tmp_path / "out.nq"
    worker._write_graph_nquads(_graph(), input_path)
    g2 = worker._read_graph_nquads(input_path)
    assert len(g2) == 1
    worker._write_graph_nquads(g2, out_path)
    assert out_path.exists()


def test_main_handles_stream_ops(monkeypatch, tmp_path: Path) -> None:
    captured: list[dict[str, object]] = []

    class Proc:
        def process_graph(self, graph, _ctx):
            graph.add(
                (
                    URIRef("https://example.com/x"),
                    URIRef("https://example.com/y"),
                    Literal("z"),
                )
            )
            return graph

    monkeypatch.setattr(worker, "_emit", lambda m: captured.append(m))
    monkeypatch.setattr(worker, "_load_class", lambda _: Proc)
    monkeypatch.setattr(
        worker, "_build_context", lambda payload: SimpleNamespace(**payload)
    )
    monkeypatch.setattr(worker, "_read_graph_nquads", lambda _: _graph())
    monkeypatch.setattr(worker, "_write_graph_nquads", lambda _g, _p: None)
    monkeypatch.setattr(
        worker.argparse.ArgumentParser,
        "parse_args",
        lambda _self: SimpleNamespace(class_path="m:Proc"),
    )

    lines = [
        "not-json\n",
        json.dumps({"op": "noop", "id": "1"}) + "\n",
        json.dumps(
            {
                "op": "process",
                "id": "2",
                "input_graph": str(tmp_path / "a.nq"),
                "output_graph": str(tmp_path / "b.nq"),
                "context": {},
            }
        )
        + "\n",
        json.dumps({"op": "shutdown"}) + "\n",
    ]
    monkeypatch.setattr("sys.stdin", io.StringIO("".join(lines)), raising=False)

    worker.main()
    assert captured[0]["op"] == "ready"
    assert captured[1]["ok"] is False
    assert captured[2]["error"] == "Unsupported operation."
    assert captured[3] == {"op": "result", "id": "2", "ok": True}
    assert captured[4] == {"op": "shutdown", "ok": True}


def test_main_ready_error(monkeypatch) -> None:
    messages: list[dict[str, object]] = []
    monkeypatch.setattr(worker, "_emit", lambda m: messages.append(m))
    monkeypatch.setattr(
        worker.argparse.ArgumentParser,
        "parse_args",
        lambda _self: SimpleNamespace(class_path="m:Missing"),
    )
    monkeypatch.setattr(
        worker, "_load_class", lambda _cp: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    try:
        worker.main()
        assert False
    except SystemExit as exc:
        assert exc.code == 1
    assert messages[0]["op"] == "ready"
    assert messages[0]["ok"] is False
