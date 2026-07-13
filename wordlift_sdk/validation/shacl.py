"""SHACL validation helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from importlib import resources
from json import JSONDecodeError
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from html.parser import HTMLParser
import json

from rdflib.collection import Collection
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, SH
from rdflib.term import Identifier
from requests import Response, get

from wordlift_sdk.render import RenderOptions, render_html

DEFAULT_OPT_IN_EXCLUDED_SHAPES = {"google-image-license-metadata.ttl"}
_SCHEMAORG_GRAMMAR_SHAPE = "schemaorg-grammar.ttl"
_SCHEMAORG_SUBCLASS_ONTOLOGY_RESOURCE = "schemaorg-subclass-ontology.nt"
_SCHEMAORG_HTTP = "http://schema.org/"
_SCHEMAORG_GRAMMAR = Namespace("https://wordlift.io/shacl/schemaorg-grammar/")
_DOMAIN_RULE_CLASS = _SCHEMAORG_GRAMMAR.PropertyDomainRule
_DOMAIN_RULE_PATH = _SCHEMAORG_GRAMMAR.path
_DOMAIN_RULE_DOMAIN = _SCHEMAORG_GRAMMAR.domain
_DOMAIN_CONSTRAINT_COMPONENT = _SCHEMAORG_GRAMMAR.PropertyDomainConstraintComponent
_VALIDATOR_OPTIONS = {
    "inference": "rdfs",
    "abort_on_first": False,
    "allow_infos": True,
    "allow_warnings": True,
}

# Prefix for synthetic @ids injected into @id-less JSON-LD nodes. The suffix is an
# RFC 6901 JSON Pointer to the node, so a focus node like
# ``urn:wl:node:/@graph/0/offers`` can be resolved against the *original*
# (un-injected) document by walking that pointer.
_SYNTHETIC_ID_PREFIX = "urn:wl:node:"


def _json_pointer_escape(key: str) -> str:
    """Escape a JSON object key for use in an RFC 6901 JSON Pointer segment."""
    return key.replace("~", "~0").replace("/", "~1")


@dataclass
class ValidationResult:
    conforms: bool
    report_text: str
    report_graph: Graph
    data_graph: Graph
    shape_source_map: dict[Identifier, str]
    warning_count: int
    shapes_graph: Graph | None = None


@dataclass
class ValidationIssue:
    level: str
    severity: str
    focus_node: str | None
    result_path: str | None
    rule_id: str | None
    rule_set: str | None
    message: str


@dataclass(frozen=True)
class PreparedShapes:
    shape_specs: tuple[str, ...]
    shapes_graph: Graph
    shape_source_map: dict[Identifier, str]


@dataclass
class PreparedValidationResult:
    conforms: bool
    report_graph: Graph
    report_text: str
    data_graph: Graph
    warning_count: int


@dataclass(frozen=True)
class _SchemaOrgDomainRule:
    source_shape: Identifier
    path: URIRef
    domains: frozenset[URIRef]


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


def assign_stable_jsonld_ids(data: object) -> object:
    """Return a copy of *data* with a deterministic ``@id`` on every ``@id``-less
    JSON-LD node, where the id is ``urn:wl:node:`` followed by an RFC 6901 JSON
    Pointer to the node (``urn:wl:node:/@graph/0/offers``).

    Without this, rdflib assigns a fresh random blank-node label to each unnamed
    node on every parse, so SHACL report focus nodes are unstable across runs and
    cannot be matched back to the source document. Injecting these ids gives every
    node a stable, resolvable handle without changing which constraints are
    evaluated (``graph.skolemize()`` runs post-parse — too late — hence the
    JSON-level injection).

    This is a **transient validation aid**: validate the returned copy, but do NOT
    persist it. Persist the original document and carry the reference on each
    finding — ``focus_node`` is then a real ``@id`` (nodes that had one) or a
    ``urn:wl:node:`` pointer (nodes that did not). Because injection only adds
    ``@id`` keys and never reorders or restructures, those pointers resolve against
    the original document, so consumers never need the mutated copy.
    """

    def walk(node: object, pointer: str) -> object:
        if isinstance(node, list):
            return [walk(item, f"{pointer}/{index}") for index, item in enumerate(node)]
        if isinstance(node, dict):
            if "@value" in node:  # literal value object, not a node
                return node
            result = dict(node)
            is_node = "@type" in result or any(
                not key.startswith("@") for key in result
            )
            if is_node and "@id" not in result:
                result["@id"] = f"{_SYNTHETIC_ID_PREFIX}{pointer or '/'}"
            for key, value in list(result.items()):
                if key in ("@id", "@type", "@context"):
                    continue
                result[key] = walk(value, f"{pointer}/{_json_pointer_escape(key)}")
            return result
        return node

    return walk(data, "")


def _load_graph_from_text(data: str, fmt: str | None) -> Graph:
    graph = Graph()
    try:
        if fmt == "json-ld":
            parsed = assign_stable_jsonld_ids(json.loads(data))
            data = json.dumps(parsed, ensure_ascii=False)
        graph.parse(data=data, format=fmt)
        return graph
    except Exception as exc:
        if fmt is None:
            raise
        raise RuntimeError(f"Failed to parse input as {fmt}: {exc}") from exc


def _load_graph(path_or_url: str) -> Graph:
    if _is_url(path_or_url):
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
    if fmt == "json-ld":
        return _load_graph_from_text(path.read_text(encoding="utf-8"), "json-ld")
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


def _default_shape_resource_names() -> list[str]:
    return [
        name
        for name in _shape_resource_names()
        if name not in DEFAULT_OPT_IN_EXCLUDED_SHAPES
    ]


def list_shape_names() -> list[str]:
    return _shape_resource_names()


def _is_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def _normalize_builtin_shape_name(
    spec: str, bundled_shapes: set[str], parameter_name: str
) -> str:
    candidate = spec if spec.endswith(".ttl") else f"{spec}.ttl"
    if candidate not in bundled_shapes:
        raise RuntimeError(f"Unknown {parameter_name} value: {spec}")
    return candidate


def resolve_shape_specs(
    builtin_shapes: Iterable[str] | None = None,
    exclude_builtin_shapes: Iterable[str] | None = None,
    extra_shapes: Iterable[str] | None = None,
) -> list[str]:
    bundled = _shape_resource_names()
    bundled_set = set(bundled)
    if builtin_shapes:
        selected = {
            _normalize_builtin_shape_name(spec, bundled_set, "builtin shape")
            for spec in builtin_shapes
        }
    else:
        selected = set(_default_shape_resource_names())
    if exclude_builtin_shapes:
        excluded = {
            _normalize_builtin_shape_name(spec, bundled_set, "excluded builtin shape")
            for spec in exclude_builtin_shapes
        }
        selected.difference_update(excluded)

    resolved = sorted(selected)
    seen = set(resolved)
    for spec in extra_shapes or []:
        if spec in seen:
            continue
        resolved.append(spec)
        seen.add(spec)
    return resolved


def _read_shape_resource(name: str) -> str | None:
    shapes_dir = resources.files("wordlift_sdk.validation.shacls")
    resource = shapes_dir.joinpath(name)
    if not resource.is_file():
        return None
    return resource.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _load_schemaorg_subclass_ontology() -> Graph | None:
    data = _read_shape_resource(_SCHEMAORG_SUBCLASS_ONTOLOGY_RESOURCE)
    if data is None:
        return None
    ontology = Graph()
    ontology.parse(data=data, format="nt")
    return _normalize_schema_org_uris(ontology)


def _normalize_schema_uri_ref(term: Identifier | None) -> URIRef | None:
    if not isinstance(term, URIRef):
        return None
    value = str(term)
    if value.startswith("https://schema.org/"):
        return URIRef("http://schema.org/" + value[len("https://schema.org/") :])
    return term


@lru_cache(maxsize=1)
def _schemaorg_subclass_map() -> dict[URIRef, set[URIRef]]:
    ontology = _load_schemaorg_subclass_ontology()
    if ontology is None:
        return {}

    subclass_map: dict[URIRef, set[URIRef]] = {}
    for child, parent in ontology.subject_objects(
        URIRef("http://www.w3.org/2000/01/rdf-schema#subClassOf")
    ):
        child_ref = _normalize_schema_uri_ref(child)
        parent_ref = _normalize_schema_uri_ref(parent)
        if child_ref is None or parent_ref is None:
            continue
        subclass_map.setdefault(child_ref, set()).add(parent_ref)
    return subclass_map


@lru_cache(maxsize=None)
def _schemaorg_superclasses(class_iri: URIRef) -> frozenset[URIRef]:
    subclass_map = _schemaorg_subclass_map()
    seen: set[URIRef] = set()
    stack = [class_iri]
    while stack:
        current = stack.pop()
        for parent in subclass_map.get(current, set()):
            if parent in seen:
                continue
            seen.add(parent)
            stack.append(parent)
    return frozenset(seen)


def _schemaorg_domain_rules(shapes_graph: Graph) -> dict[URIRef, _SchemaOrgDomainRule]:
    rules: dict[URIRef, _SchemaOrgDomainRule] = {}
    for source_shape in shapes_graph.subjects(RDF.type, _DOMAIN_RULE_CLASS):
        path = shapes_graph.value(source_shape, _DOMAIN_RULE_PATH)
        if not isinstance(path, URIRef):
            continue
        domains = frozenset(
            domain
            for domain in shapes_graph.objects(source_shape, _DOMAIN_RULE_DOMAIN)
            if isinstance(domain, URIRef)
        )
        if domains:
            rules[path] = _SchemaOrgDomainRule(
                source_shape=source_shape,
                path=path,
                domains=domains,
            )
    return rules


def _schemaorg_local_name(uri: URIRef) -> str:
    value = str(uri)
    return value[len(_SCHEMAORG_HTTP) :] if value.startswith(_SCHEMAORG_HTTP) else value


def _rdf_term_sort_key(term: Identifier) -> tuple[str, str, str, str]:
    return (
        term.__class__.__name__,
        str(term),
        str(getattr(term, "datatype", "") or ""),
        str(getattr(term, "language", "") or ""),
    )


def _append_schemaorg_domain_results(
    *,
    data_graph: Graph,
    report_graph: Graph,
    rules: dict[URIRef, _SchemaOrgDomainRule],
) -> list[str]:
    messages: list[str] = []
    report_node = next(report_graph.subjects(RDF.type, SH.ValidationReport), None)
    for focus_node in sorted(set(data_graph.subjects()), key=str):
        declared_types = sorted(
            {
                type_iri
                for type_iri in data_graph.objects(focus_node, RDF.type)
                if isinstance(type_iri, URIRef)
                and str(type_iri).startswith(_SCHEMAORG_HTTP)
            },
            key=str,
        )
        if not declared_types:
            continue
        for path in sorted(set(data_graph.predicates(focus_node)), key=str):
            rule = rules.get(path) if isinstance(path, URIRef) else None
            if rule is None:
                continue
            if any(
                declared_type in rule.domains
                or bool(
                    rule.domains.intersection(_schemaorg_superclasses(declared_type))
                )
                for declared_type in declared_types
            ):
                continue

            property_name = _schemaorg_local_name(rule.path)
            type_name = _schemaorg_local_name(declared_types[0])
            message = (
                f"The property {property_name} is not recognized by the schema "
                f"(e.g. schema.org) for an object of type {type_name}."
            )
            result_node = BNode()
            report_graph.add((result_node, RDF.type, SH.ValidationResult))
            report_graph.add((result_node, SH.resultSeverity, SH.Warning))
            report_graph.add((result_node, SH.focusNode, focus_node))
            report_graph.add((result_node, SH.resultPath, rule.path))
            report_graph.add((result_node, SH.sourceShape, rule.source_shape))
            report_graph.add(
                (
                    result_node,
                    SH.sourceConstraintComponent,
                    _DOMAIN_CONSTRAINT_COMPONENT,
                )
            )
            report_graph.add((result_node, SH.resultMessage, Literal(message)))
            values = sorted(
                data_graph.objects(focus_node, path),
                key=_rdf_term_sort_key,
            )
            if values:
                report_graph.add((result_node, SH.value, values[0]))
            if report_node is not None:
                report_graph.add((report_node, SH.result, result_node))
            messages.append(message)
    return messages


def _shape_expected_classes(
    shapes_graph: Graph, source_shape: Identifier
) -> set[URIRef]:
    expected: set[URIRef] = set()
    list_node = shapes_graph.value(source_shape, SH["or"])
    if list_node is None:
        return expected
    try:
        members = Collection(shapes_graph, list_node)
    except Exception:
        return expected

    for member in members:
        class_term = shapes_graph.value(member, SH["class"])
        class_ref = _normalize_schema_uri_ref(class_term)
        if class_ref is not None:
            expected.add(class_ref)
    return expected


def _should_skip_schemaorg_subclass_range_warning(
    *,
    report_graph: Graph,
    node: Identifier,
    source_map: dict[Identifier, str],
    data_graph: Graph | None,
    shapes_graph: Graph | None,
) -> bool:
    if data_graph is None or shapes_graph is None:
        return False

    source_shape = report_graph.value(node, SH.sourceShape)
    if source_shape is None:
        return False
    shape_source = source_map.get(source_shape) or source_map.get(str(source_shape))
    if shape_source != _SCHEMAORG_GRAMMAR_SHAPE.removesuffix(".ttl"):
        return False

    message = report_graph.value(node, SH.resultMessage)
    if not isinstance(message, Identifier) or not str(message).startswith(
        "Schema.org range check:"
    ):
        return False

    value = report_graph.value(node, SH.value)
    value_ref = _normalize_schema_uri_ref(value)
    if value_ref is None:
        return False

    expected_classes = _shape_expected_classes(shapes_graph, source_shape)
    if not expected_classes:
        return False

    value_types = {
        type_ref
        for type_ref in (
            _normalize_schema_uri_ref(term)
            for term in data_graph.objects(value_ref, RDF.type)
        )
        if type_ref is not None
    }
    if not value_types:
        return False

    for value_type in value_types:
        if value_type in expected_classes:
            return True
        if expected_classes.intersection(_schemaorg_superclasses(value_type)):
            return True
    return False


def _resolve_shape_sources(shape_specs: Iterable[str] | None) -> list[str]:
    if not shape_specs:
        return _default_shape_resource_names()

    resolved: list[str] = []
    for spec in shape_specs:
        path = Path(spec)
        if path.exists():
            resolved.append(path.as_posix())
            continue
        if _is_url(spec):
            resolved.append(spec)
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
            temp = _load_graph(path.as_posix())
            shapes_graph += temp
            label = path.stem
            for subj in temp.subjects():
                source_map.setdefault(subj, label)
            continue
        if _is_url(spec):
            temp = _load_graph(spec)
            shapes_graph += temp
            parsed = urlparse(spec)
            label = Path(parsed.path).stem or parsed.netloc or spec
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


@lru_cache(maxsize=32)
def _prepare_shapes_cached(resolved_shape_specs: tuple[str, ...]) -> PreparedShapes:
    shapes_graph, source_map = _load_shapes_graph(resolved_shape_specs)
    return PreparedShapes(
        shape_specs=resolved_shape_specs,
        shapes_graph=shapes_graph,
        shape_source_map=source_map,
    )


def prepare_shapes(shape_specs: Iterable[str] | None = None) -> PreparedShapes:
    return _prepare_shapes_cached(tuple(_resolve_shape_sources(shape_specs)))


class PreparedShaclValidator:
    """Reusable SHACL validator with cached shape loading and warmed shape harvest."""

    def __init__(self, prepared_shapes: PreparedShapes):
        from pyshacl import Validator

        self._prepared_shapes = prepared_shapes
        self._schemaorg_domain_rules = _schemaorg_domain_rules(
            prepared_shapes.shapes_graph
        )
        self._validator = Validator(
            Graph(),
            shacl_graph=prepared_shapes.shapes_graph,
            options=dict(_VALIDATOR_OPTIONS),
        )
        _ = self._validator.shacl_graph.shapes

    @classmethod
    def from_shape_specs(
        cls, shape_specs: Iterable[str] | None = None
    ) -> "PreparedShaclValidator":
        return cls(prepare_shapes(shape_specs))

    @property
    def prepared_shapes(self) -> PreparedShapes:
        return self._prepared_shapes

    def validate_graph(
        self,
        data_graph: Graph,
        *,
        normalize_schema_org: bool = True,
    ) -> PreparedValidationResult:
        if normalize_schema_org:
            data_graph = _normalize_schema_org_uris(data_graph)

        self._validator.data_graph = data_graph
        self._validator.pre_inferenced = False
        self._validator._target_graph = None

        conforms, report_graph, report_text = self._validator.run()
        domain_messages = _append_schemaorg_domain_results(
            data_graph=data_graph,
            report_graph=report_graph,
            rules=self._schemaorg_domain_rules,
        )
        if domain_messages:
            report_text = "\n".join(
                [
                    report_text.rstrip(),
                    *(f"Domain warning: {m}" for m in domain_messages),
                ]
            )
        warning_count = sum(
            1 for _ in report_graph.subjects(SH.resultSeverity, SH.Warning)
        )

        return PreparedValidationResult(
            conforms=conforms,
            report_graph=report_graph,
            report_text=report_text,
            data_graph=data_graph,
            warning_count=warning_count,
        )


def validate_file(
    input_file: str, shape_specs: Iterable[str] | None = None
) -> ValidationResult:
    data_graph = _load_graph(input_file)
    validator = PreparedShaclValidator.from_shape_specs(shape_specs)
    result = validator.validate_graph(data_graph)

    return ValidationResult(
        conforms=result.conforms,
        report_text=result.report_text,
        report_graph=result.report_graph,
        data_graph=result.data_graph,
        shape_source_map=validator.prepared_shapes.shape_source_map,
        warning_count=result.warning_count,
        shapes_graph=validator.prepared_shapes.shapes_graph,
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
    validator = PreparedShaclValidator.from_shape_specs(shape_specs)
    result = validator.validate_graph(data_graph)

    return ValidationResult(
        conforms=result.conforms,
        report_text=result.report_text,
        report_graph=result.report_graph,
        data_graph=result.data_graph,
        shape_source_map=validator.prepared_shapes.shape_source_map,
        warning_count=result.warning_count,
        shapes_graph=validator.prepared_shapes.shapes_graph,
    )


def _severity_to_level(severity: Identifier | None) -> str:
    if severity == SH.Violation:
        return "error"
    return "warning"


def extract_validation_issues(result: ValidationResult) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for node in result.report_graph.subjects(SH.resultSeverity, None):
        if _should_skip_schemaorg_subclass_range_warning(
            report_graph=result.report_graph,
            node=node,
            source_map=result.shape_source_map,
            data_graph=result.data_graph,
            shapes_graph=result.shapes_graph,
        ):
            continue
        severity = result.report_graph.value(node, SH.resultSeverity)
        source_shape = result.report_graph.value(node, SH.sourceShape)
        message = result.report_graph.value(node, SH.resultMessage)
        issues.append(
            ValidationIssue(
                level=_severity_to_level(severity),
                severity=str(severity) if severity else str(SH.Violation),
                focus_node=str(result.report_graph.value(node, SH.focusNode))
                if result.report_graph.value(node, SH.focusNode) is not None
                else None,
                result_path=str(result.report_graph.value(node, SH.resultPath))
                if result.report_graph.value(node, SH.resultPath) is not None
                else None,
                rule_id=str(source_shape) if source_shape is not None else None,
                rule_set=result.shape_source_map.get(source_shape)
                if source_shape is not None
                else None,
                message=str(message) if message is not None else "",
            )
        )
    return issues


def filter_validation_issues(
    issues: Iterable[ValidationIssue], level: str = "warning"
) -> list[ValidationIssue]:
    if level not in {"warning", "error"}:
        raise RuntimeError(f"Unsupported level: {level}")
    if level == "warning":
        return list(issues)
    return [issue for issue in issues if issue.level == "error"]
