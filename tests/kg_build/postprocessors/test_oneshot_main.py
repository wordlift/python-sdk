from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from rdflib import Graph, Literal, URIRef

from wordlift_sdk.kg_build.postprocessors import oneshot as runner


def _graph() -> Graph:
    g = Graph()
    g.add(
        (URIRef("https://example.com/s"), URIRef("https://example.com/p"), Literal("v"))
    )
    return g


def test_main_success(monkeypatch, tmp_path: Path) -> None:
    context_path = tmp_path / "context.json"
    context_path.write_text(
        json.dumps({"profile_name": "p", "url": "https://example.com"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runner.argparse.ArgumentParser,
        "parse_args",
        lambda _self: SimpleNamespace(
            class_path="x:Proc",
            input_graph=str(tmp_path / "in.nq"),
            output_graph=str(tmp_path / "out.nq"),
            context=str(context_path),
        ),
    )
    monkeypatch.setattr(runner, "_build_context", lambda payload: payload)
    monkeypatch.setattr(runner, "_read_graph_nquads", lambda _p: _graph())

    class Proc:
        def process_graph(self, graph, _context):
            return graph

    monkeypatch.setattr(runner, "_load_class", lambda _cp: Proc)
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        runner,
        "_write_graph_nquads",
        lambda graph, path: captured.update({"len": len(graph), "path": str(path)}),
    )

    runner.main()
    assert captured["len"] == 1
    assert captured["path"].endswith("out.nq")


def test_main_failure_exits(monkeypatch, tmp_path: Path, capsys) -> None:
    context_path = tmp_path / "context.json"
    context_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        runner.argparse.ArgumentParser,
        "parse_args",
        lambda _self: SimpleNamespace(
            class_path="x:Proc",
            input_graph=str(tmp_path / "in.nq"),
            output_graph=str(tmp_path / "out.nq"),
            context=str(context_path),
        ),
    )
    monkeypatch.setattr(runner, "_read_graph_nquads", lambda _p: _graph())
    monkeypatch.setattr(
        runner, "_load_class", lambda _cp: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    try:
        runner.main()
        assert False
    except SystemExit as exc:
        assert exc.code == 1
    assert "boom" in capsys.readouterr().err
