from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import json
import sys
import traceback
from pathlib import Path
from typing import Any

from rdflib import Dataset, Graph

from .postprocessor_runner import _build_context


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


def _emit(message: dict[str, Any]) -> None:
    print(json.dumps(message, ensure_ascii=True, default=str), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Persistent postprocessor worker.")
    parser.add_argument("--class", dest="class_path", required=True)
    args = parser.parse_args()

    try:
        processor_class = _load_class(args.class_path)
        processor = processor_class()
        _emit({"op": "ready", "ok": True})
    except Exception as exc:  # pragma: no cover - process boundary
        _emit({"op": "ready", "ok": False, "error": str(exc)})
        raise SystemExit(1) from exc

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            _emit(
                {
                    "op": "result",
                    "id": None,
                    "ok": False,
                    "error": "Invalid JSON payload.",
                }
            )
            continue

        op = payload.get("op")
        if op == "shutdown":
            _emit({"op": "shutdown", "ok": True})
            return
        if op != "process":
            _emit(
                {
                    "op": "result",
                    "id": payload.get("id"),
                    "ok": False,
                    "error": "Unsupported operation.",
                }
            )
            continue

        job_id = payload.get("id")
        try:
            input_graph_path = Path(str(payload["input_graph"]))
            output_graph_path = Path(str(payload["output_graph"]))
            context_payload = payload.get("context", {})
            if not isinstance(context_payload, dict):
                raise TypeError("context must be an object")

            context = _build_context(context_payload)
            graph = _read_graph_nquads(input_graph_path)
            result = processor.process_graph(graph, context)
            if inspect.isawaitable(result):
                result = asyncio.run(result)
            output_graph = graph if result is None else result
            _write_graph_nquads(output_graph, output_graph_path)

            _emit({"op": "result", "id": job_id, "ok": True})
        except Exception as exc:  # pragma: no cover - process boundary
            _emit(
                {
                    "op": "result",
                    "id": job_id,
                    "ok": False,
                    "error": f"{exc}\n{traceback.format_exc()}".strip(),
                }
            )


if __name__ == "__main__":
    main()
