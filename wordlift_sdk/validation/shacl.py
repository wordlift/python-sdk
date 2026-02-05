"""SHACL validation helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from importlib import resources
from json import JSONDecodeError
from pathlib import Path
from typing import Iterable

from html.parser import HTMLParser
import json

from pyshacl import validate
from rdflib import Graph, Namespace, URIRef
from rdflib.term import Identifier
from requests import Response, get

from wordlift_sdk.render import RenderOptions, render_html


@dataclass
class ValidationResult:
    conforms: bool
    report_text: str
    report_graph: Graph
    data_graph: Graph
    shape_source_map: dict[Identifier, str]
    warning_count: int


class _JsonLdScriptExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.fragments: list[str] = []
        self._in_jsonld = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        attrs_map = {key.lower(): value for key, value in attrs}
        script_type = (attrs_map.get("type") or "").lower()
        self._in_jsonld = "ld+json" in script_type

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script":
            self._in_jsonld = False

    def handle_data(self, data: str) -> None:
        if self._in_jsonld:
            stripped = data.strip()
            if stripped:
                self.fragments.append(stripped)


def _detect_format_from_path(path: Path) -> str | None:
    if path.suffix.lower() in {".jsonld", ".json-ld"}:
        return "json-ld"
    if path.suffix.lower() in {".ttl", ".turtle"}:
        return "turtle"
    if path.suffix.lower() in {".nt"}:
        return "nt"
    return None


def _detect_format_from_response(response: Response) -> str | None:
    content_type = response.headers.get("content-type", "").lower()
    if "json" in content_type or "ld+json" in content_type:
        return "json-ld"
    if "turtle" in content_type or "ttl" in content_type:
        return "turtle"
    if "n-triples" in content_type:
        return "nt"
    return None


def _load_graph_from_text(data: str, fmt: str | None) -> Graph:
    graph = Graph()
    try:
        graph.parse(data=data, format=fmt)
        return graph
    except Exception as exc:
        if fmt is None:
            raise
        raise RuntimeError(f"Failed to parse input as {fmt}: {exc}") from exc


def _load_graph(path_or_url: str) -> Graph:
    if path_or_url.startswith(("http://", "https://")):
        response = get(path_or_url, timeout=30)
        if not response.ok:
            raise RuntimeError(
                f"Failed to fetch URL ({response.status_code}): {path_or_url}"
            )
        fmt = _detect_format_from_response(response)
        try:
            return _load_graph_from_text(response.text, fmt)
        except Exception:
            for fallback in (None, "json-ld", "turtle", "nt"):
                if fallback == fmt:
                    continue
                try:
                    return _load_graph_from_text(response.text, fallback)
                except Exception:
                    continue
            raise RuntimeError(f"Failed to parse remote RDF from {path_or_url}")

    path = Path(path_or_url)
    if not path.exists():
        raise RuntimeError(f"Input file not found: {path}")

    fmt = _detect_format_from_path(path)
    graph = Graph()
    graph.parse(path.as_posix(), format=fmt)
    return graph


def _load_graph_from_jsonld(data: dict | list) -> Graph:
    payload = json.dumps(data, ensure_ascii=False)
    return _load_graph_from_text(payload, "json-ld")


def _normalize_schema_org_uris(graph: Graph) -> Graph:
    schema_http = "http://schema.org/"
    schema_https = "https://schema.org/"
    normalized = Graph()
    for prefix, ns in graph.namespace_manager.namespaces():
        normalized.namespace_manager.bind(prefix, ns, replace=True)
    for s, p, o in graph:
        if isinstance(s, URIRef) and str(s).startswith(schema_https):
            s = URIRef(schema_http + str(s)[len(schema_https) :])
        if isinstance(p, URIRef) and str(p).startswith(schema_https):
            p = URIRef(schema_http + str(p)[len(schema_https) :])
        if isinstance(o, URIRef) and str(o).startswith(schema_https):
            o = URIRef(schema_http + str(o)[len(schema_https) :])
        normalized.add((s, p, o))
    return normalized


def _extract_jsonld_fragments(html: str) -> list[str]:
    parser = _JsonLdScriptExtractor()
    parser.feed(html)
    return parser.fragments


def _flatten_jsonld_fragment(data: object) -> list[dict]:
    if isinstance(data, list):
        return [node for node in data if isinstance(node, dict)]
    if isinstance(data, dict):
        if "@graph" in data and isinstance(data["@graph"], list):
            context = data.get("@context")
            nodes: list[dict] = []
            for node in data["@graph"]:
                if not isinstance(node, dict):
                    continue
                if context is None or "@context" in node:
                    nodes.append(node)
                else:
                    enriched = dict(node)
                    enriched["@context"] = context
                    nodes.append(enriched)
            return nodes
        return [data]
    return []


def _parse_jsonld_fragments(fragments: Iterable[str], url: str) -> list[dict]:
    nodes: list[dict] = []
    for idx, fragment in enumerate(fragments, start=1):
        try:
            parsed = json.loads(fragment)
        except JSONDecodeError as exc:
            raise RuntimeError(
                f"Invalid JSON-LD fragment #{idx} extracted from {url}: {exc}"
            ) from exc
        nodes.extend(_flatten_jsonld_fragment(parsed))
    return nodes


def _shape_resource_names() -> list[str]:
    shapes_dir = resources.files("wordlift_sdk.validation.shacls")
    return sorted(
        [
            p.name
            for p in shapes_dir.iterdir()
            if p.is_file() and p.name.endswith(".ttl")
        ]
    )


def list_shape_names() -> list[str]:
    return _shape_resource_names()


def _read_shape_resource(name: str) -> str | None:
    shapes_dir = resources.files("wordlift_sdk.validation.shacls")
    resource = shapes_dir.joinpath(name)
    if not resource.is_file():
        return None
    return resource.read_text(encoding="utf-8")


def _resolve_shape_sources(shape_specs: Iterable[str] | None) -> list[str]:
    if not shape_specs:
        return _shape_resource_names()

    resolved: list[str] = []
    for spec in shape_specs:
        path = Path(spec)
        if path.exists():
            resolved.append(path.as_posix())
            continue

        name = spec
        if not name.endswith(".ttl"):
            name = f"{name}.ttl"

        if _read_shape_resource(name) is None:
            raise RuntimeError(f"Shape not found: {spec}")
        resolved.append(name)

    return resolved


def _load_shapes_graph(
    shape_specs: Iterable[str] | None,
) -> tuple[Graph, dict[Identifier, str]]:
    shapes_graph = Graph()
    source_map: dict[Identifier, str] = {}
    for spec in _resolve_shape_sources(shape_specs):
        path = Path(spec)
        if path.exists():
            temp = Graph()
            temp.parse(path.as_posix(), format="turtle")
            shapes_graph += temp
            label = path.stem
            for subj in temp.subjects():
                source_map.setdefault(subj, label)
            continue

        data = _read_shape_resource(spec)
        if data is None:
            raise RuntimeError(f"Shape not found: {spec}")
        temp = Graph()
        temp.parse(data=data, format="turtle")
        shapes_graph += temp
        label = Path(spec).stem
        for subj in temp.subjects():
            source_map.setdefault(subj, label)

    return shapes_graph, source_map


def validate_file(
    input_file: str, shape_specs: Iterable[str] | None = None
) -> ValidationResult:
    data_graph = _load_graph(input_file)
    data_graph = _normalize_schema_org_uris(data_graph)
    shapes_graph, source_map = _load_shapes_graph(shape_specs)

    conforms, report_graph, report_text = validate(
        data_graph,
        shacl_graph=shapes_graph,
        inference="rdfs",
        abort_on_first=False,
        allow_infos=True,
        allow_warnings=True,
    )

    sh = Namespace("http://www.w3.org/ns/shacl#")
    warning_count = sum(1 for _ in report_graph.subjects(sh.resultSeverity, sh.Warning))

    return ValidationResult(
        conforms=conforms,
        report_text=report_text,
        report_graph=report_graph,
        data_graph=data_graph,
        shape_source_map=source_map,
        warning_count=warning_count,
    )


def validate_jsonld_from_url(
    url: str,
    shape_specs: Iterable[str] | None = None,
    render_options: RenderOptions | None = None,
) -> ValidationResult:
    options = render_options or RenderOptions(url=url)
    if options.url != url:
        options = replace(options, url=url)
    rendered = render_html(options)
    fragments = _extract_jsonld_fragments(rendered.html)
    if not fragments:
        raise RuntimeError(f"No JSON-LD fragments found in rendered HTML for {url}")
    nodes = _parse_jsonld_fragments(fragments, url)
    if not nodes:
        raise RuntimeError(f"No JSON-LD nodes found in rendered HTML for {url}")
    data_graph = _load_graph_from_jsonld(nodes)
    data_graph = _normalize_schema_org_uris(data_graph)
    shapes_graph, source_map = _load_shapes_graph(shape_specs)

    conforms, report_graph, report_text = validate(
        data_graph,
        shacl_graph=shapes_graph,
        inference="rdfs",
        abort_on_first=False,
        allow_infos=True,
        allow_warnings=True,
    )

    sh = Namespace("http://www.w3.org/ns/shacl#")
    warning_count = sum(1 for _ in report_graph.subjects(sh.resultSeverity, sh.Warning))

    return ValidationResult(
        conforms=conforms,
        report_text=report_text,
        report_graph=report_graph,
        data_graph=data_graph,
        shape_source_map=source_map,
        warning_count=warning_count,
    )
