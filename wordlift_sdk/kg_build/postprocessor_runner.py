from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from rdflib import Dataset, Graph

from .id_allocator import IdAllocator
from .postprocessors import PostprocessorContext


def _build_context(payload: dict[str, Any]) -> PostprocessorContext:
    dataset_uri = str(payload.get("dataset_uri", "")).rstrip("/")
    settings = dict(payload.get("settings", {}) or {})
    settings.setdefault("api_url", "https://api.wordlift.io")
    account = SimpleNamespace(
        dataset_uri=dataset_uri,
        country_code=str(payload.get("country_code", "")).strip().lower(),
        key=payload.get("account_key"),
    )
    response_payload = payload.get("response", {}) or {}
    web_page_payload = response_payload.get("web_page", {}) or {}
    response = SimpleNamespace(
        id=response_payload.get("id"),
        web_page=SimpleNamespace(
            url=web_page_payload.get("url"),
            html=web_page_payload.get("html"),
        ),
    )
    return PostprocessorContext(
        profile_name=str(payload.get("profile_name", "")),
        url=str(payload.get("url", "")),
        account=account,
        exports=dict(payload.get("exports", {}) or {}),
        response=response,
        existing_web_page_id=(
            str(payload.get("existing_web_page_id"))
            if payload.get("existing_web_page_id")
            else None
        ),
        settings=settings,
        ids=IdAllocator(dataset_uri) if dataset_uri else None,
    )


def _load_class(class_path: str):
    if ":" not in class_path:
        raise ValueError("class path must be 'package.module:ClassName'")
    module_name, class_name = class_path.split(":", 1)
    module = importlib.import_module(module_name)
    klass = getattr(module, class_name, None)
    if klass is None:
        raise AttributeError(
            f"Class '{class_name}' not found in module '{module_name}'."
        )
    return klass


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Execute a postprocessor class against N-Quads graph files."
    )
    parser.add_argument("--class", dest="class_path", required=True)
    parser.add_argument("--input-graph", required=True)
    parser.add_argument("--output-graph", required=True)
    parser.add_argument("--context", required=True)
    args = parser.parse_args()

    try:
        context_payload = json.loads(Path(args.context).read_text(encoding="utf-8"))
        context = _build_context(context_payload)

        graph = _read_graph_nquads(Path(args.input_graph))

        processor_class = _load_class(args.class_path)
        processor = processor_class()
        result = processor.process_graph(graph, context)
        output_graph = graph if result is None else result
        _write_graph_nquads(output_graph, Path(args.output_graph))
    except Exception as exc:  # pragma: no cover - process boundary
        print(f"[postprocessor_runner] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def _read_graph_nquads(path: Path) -> Graph:
    dataset = Dataset()
    dataset.parse(path, format="nquads")
    graph = Graph()
    for triple in dataset.triples((None, None, None)):
        graph.add(triple)
    return graph


def _write_graph_nquads(graph: Graph, path: Path) -> None:
    dataset = Dataset()
    for triple in graph:
        dataset.add(triple)
    dataset.serialize(destination=path, format="nquads")


if __name__ == "__main__":
    main()
