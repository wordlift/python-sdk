"""Output utilities for structured data workflows."""

from __future__ import annotations

from pathlib import Path

from rdflib import Graph


_OUTPUT_FORMATS: dict[str, tuple[str, str]] = {
    "ttl": ("turtle", "ttl"),
    "jsonld": ("json-ld", "jsonld"),
    "json-ld": ("json-ld", "jsonld"),
    "rdf": ("xml", "rdf"),
    "nt": ("nt", "nt"),
    "nq": ("nquads", "nq"),
}


def write_output(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def default_output_paths(out_dir: Path, base_name: str) -> tuple[Path, Path]:
    jsonld_path = out_dir / f"{base_name}.jsonld"
    yarrml_path = out_dir / f"{base_name}.yarrml"
    return jsonld_path, yarrml_path


def normalize_output_format(value: str) -> tuple[str, str]:
    key = value.strip().lower()
    if key not in _OUTPUT_FORMATS:
        supported = ", ".join(sorted({k for k in _OUTPUT_FORMATS if "-" not in k}))
        raise RuntimeError(f"Unsupported format '{value}'. Choose from: {supported}.")
    return _OUTPUT_FORMATS[key]


def serialize_graph(graph: Graph, output_format: str) -> str:
    rdflib_format, _ = normalize_output_format(output_format)
    serialized = graph.serialize(format=rdflib_format)
    if isinstance(serialized, bytes):
        return serialized.decode("utf-8")
    return serialized
