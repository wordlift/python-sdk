"""Generate structured data from a rendered web page."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import wordlift_client
from wordlift_client import ApiClient, Configuration
from wordlift_client import AgentApi
from wordlift_client.models.ask_request import AskRequest
from rdflib import Graph, Namespace, RDF
from rdflib.term import BNode, Identifier, Literal, URIRef

from wordlift_sdk.structured_data.constants import DEFAULT_BASE_URL
from wordlift_sdk.validation.shacl import ValidationResult, validate_file


_SCHEMA_BASE = "https://schema.org"
_SCHEMA_HTTP = "http://schema.org/"
_AGENT_BASE_URL = "https://api.wordlift.io/agent"
_AGENT_MODEL = "gpt-5.1"
_RR = Namespace("http://www.w3.org/ns/r2rml#")
_RML = Namespace("http://w3id.org/rml/")
_RML_LEGACY = Namespace("http://semweb.mmlab.be/ns/rml#")
_QL = Namespace("http://semweb.mmlab.be/ns/ql#")
_SH = Namespace("http://www.w3.org/ns/shacl#")
_REVIEW_OPTIONAL_EXTRAS = {
    "description",
    "positiveNotes",
    "negativeNotes",
    "reviewBody",
    "image",
    "inLanguage",
    "publisher",
    "datePublished",
}


@dataclass
class StructuredDataOptions:
    url: str
    target_type: str | None
    dataset_uri: str
    headless: bool = True
    timeout_ms: int = 30000
    wait_until: str = "networkidle"
    max_retries: int = 2
    max_xhtml_chars: int = 40000
    max_text_node_chars: int = 400
    max_nesting_depth: int = 2
    verbose: bool = True


@dataclass
class StructuredDataResult:
    jsonld: dict[str, Any]
    yarrml: str
    jsonld_filename: str
    yarrml_filename: str


def _build_client(api_key: str, base_url: str) -> ApiClient:
    config = Configuration(host=base_url)
    config.api_key["ApiKey"] = api_key
    config.api_key_prefix["ApiKey"] = "Key"
    return ApiClient(config)


def _build_agent_client(api_key: str) -> ApiClient:
    config = Configuration(host=_AGENT_BASE_URL)
    config.api_key["ApiKey"] = api_key
    config.api_key_prefix["ApiKey"] = "Key"
    return ApiClient(config)


async def get_dataset_uri_async(api_key: str, base_url: str = DEFAULT_BASE_URL) -> str:
    async with _build_client(api_key, base_url) as api_client:
        api = wordlift_client.AccountApi(api_client)
        account = await api.get_me()
    dataset_uri = getattr(account, "dataset_uri", None)
    if not dataset_uri:
        raise RuntimeError("Failed to resolve dataset_uri from account get_me.")
    return dataset_uri


def get_dataset_uri(api_key: str, base_url: str = DEFAULT_BASE_URL) -> str:
    return asyncio.run(get_dataset_uri_async(api_key, base_url))


def normalize_type(value: str) -> str:
    value = value.strip()
    if value.startswith("schema:"):
        return value.split(":", 1)[1]
    if value.startswith("http://schema.org/"):
        return value.split("/", 3)[-1]
    if value.startswith("https://schema.org/"):
        return value.split("/", 3)[-1]
    return value


_GOOGLE_SHAPES_CACHE: Graph | None = None
_SCHEMA_SHAPES_CACHE: Graph | None = None
_SCHEMA_PROP_CACHE: set[str] | None = None
_SCHEMA_RANGE_CACHE: dict[str, dict[str, set[str]]] | None = None


def _load_google_shapes() -> Graph:
    global _GOOGLE_SHAPES_CACHE
    if _GOOGLE_SHAPES_CACHE is not None:
        return _GOOGLE_SHAPES_CACHE
    graph = Graph()
    shapes_dir = resources.files("wordlift_sdk.validation.shacls")
    for entry in shapes_dir.iterdir():
        if not entry.is_file() or not entry.name.endswith(".ttl"):
            continue
        if entry.name.startswith("google-") or entry.name == "review-snippet.ttl":
            graph.parse(data=entry.read_text(encoding="utf-8"), format="turtle")
    _GOOGLE_SHAPES_CACHE = graph
    return graph


def _load_schema_shapes() -> Graph:
    global _SCHEMA_SHAPES_CACHE
    if _SCHEMA_SHAPES_CACHE is not None:
        return _SCHEMA_SHAPES_CACHE
    graph = Graph()
    shapes_dir = resources.files("wordlift_sdk.validation.shacls")
    schema_path = shapes_dir.joinpath("schemaorg-grammar.ttl")
    if not schema_path.is_file():
        raise RuntimeError(
            "schemaorg-grammar.ttl not found. Regenerate with scripts/generate_schema_shacls.py."
        )
    graph.parse(data=schema_path.read_text(encoding="utf-8"), format="turtle")
    _SCHEMA_SHAPES_CACHE = graph
    return graph


def _schema_property_set() -> set[str]:
    global _SCHEMA_PROP_CACHE
    if _SCHEMA_PROP_CACHE is not None:
        return _SCHEMA_PROP_CACHE
    graph = _load_schema_shapes()
    props: set[str] = set()
    for prop in graph.objects(None, _SH.path):
        name = _path_to_string(graph, prop)
        if not name:
            continue
        props.add(name)
        props.add(name.split(".", 1)[0])
    _SCHEMA_PROP_CACHE = props
    return props


def _rdf_list_items(graph: Graph, head: Identifier) -> list[Identifier]:
    items: list[Identifier] = []
    current: Identifier | None = head
    while current and current != RDF.nil:
        first = graph.value(current, RDF.first)
        if first is None:
            break
        items.append(first)
        current = graph.value(current, RDF.rest)
    return items


def _schema_property_ranges() -> dict[str, dict[str, set[str]]]:
    global _SCHEMA_RANGE_CACHE
    if _SCHEMA_RANGE_CACHE is not None:
        return _SCHEMA_RANGE_CACHE
    graph = _load_schema_shapes()
    ranges: dict[str, dict[str, set[str]]] = {}
    for shape in graph.subjects(_SH.targetClass, None):
        target_class = graph.value(shape, _SH.targetClass)
        type_name = _short_schema_name(target_class)
        if not type_name:
            continue
        for prop in graph.objects(shape, _SH.property):
            path = graph.value(prop, _SH.path)
            if path is None:
                continue
            prop_name = _path_to_string(graph, path)
            if not prop_name:
                continue
            or_list = graph.value(prop, _SH["or"])
            if or_list is None:
                continue
            for item in _rdf_list_items(graph, or_list):
                class_node = graph.value(item, _SH["class"])
                class_name = _short_schema_name(class_node)
                if not class_name:
                    continue
                ranges.setdefault(type_name, {}).setdefault(prop_name, set()).add(
                    class_name
                )
    _SCHEMA_RANGE_CACHE = ranges
    return ranges


def _short_schema_name(value: Identifier) -> str | None:
    if not isinstance(value, URIRef):
        return None
    text = str(value)
    if text.startswith(_SCHEMA_BASE):
        return text[len(_SCHEMA_BASE) + 1 :]
    if text.startswith(_SCHEMA_HTTP):
        return text[len(_SCHEMA_HTTP) :]
    return None


def _path_to_string(graph: Graph, path: Identifier) -> str | None:
    if isinstance(path, URIRef):
        return _short_schema_name(path)
    if isinstance(path, BNode):
        parts: list[str] = []
        current: Identifier | None = path
        while current and current != RDF.nil:
            first = graph.value(current, RDF.first)
            if first is None:
                break
            name = _short_schema_name(first)
            if not name:
                break
            parts.append(name)
            current = graph.value(current, RDF.rest)
        if parts:
            return ".".join(parts)
    return None


def _property_guide_for_type(type_name: str) -> dict[str, list[str]]:
    type_name = normalize_type(type_name)
    targets = {
        URIRef(f"{_SCHEMA_BASE}/{type_name}"),
        URIRef(f"{_SCHEMA_HTTP}{type_name}"),
    }

    required: set[str] = set()
    recommended: set[str] = set()
    google_graph = _load_google_shapes()
    for target in targets:
        for shape in google_graph.subjects(_SH.targetClass, target):
            for prop in google_graph.objects(shape, _SH.property):
                path = google_graph.value(prop, _SH.path)
                if path is None:
                    continue
                min_count = google_graph.value(prop, _SH.minCount)
                if isinstance(min_count, Literal):
                    try:
                        if int(min_count) < 1:
                            continue
                    except Exception:
                        continue
                else:
                    continue
                prop_name = _path_to_string(google_graph, path)
                if not prop_name:
                    continue
                severity = google_graph.value(prop, _SH.severity)
                if severity == _SH.Warning:
                    recommended.add(prop_name)
                else:
                    required.add(prop_name)

    schema_props: set[str] = set()
    schema_graph = _load_schema_shapes()
    for target in targets:
        for shape in schema_graph.subjects(_SH.targetClass, target):
            for prop in schema_graph.objects(shape, _SH.property):
                path = schema_graph.value(prop, _SH.path)
                if path is None:
                    continue
                prop_name = _path_to_string(schema_graph, path)
                if not prop_name:
                    continue
                schema_props.add(prop_name)

    optional = sorted(schema_props.difference(required).difference(recommended))

    return {
        "required": sorted(required),
        "recommended": sorted(recommended),
        "optional": optional,
        "schema": sorted(schema_props),
    }


def _related_types_for_type(
    type_name: str,
    property_guide: dict[str, list[str]],
    ranges: dict[str, dict[str, set[str]]],
) -> list[str]:
    related: set[str] = set()
    prop_ranges = ranges.get(type_name, {})
    prop_candidates = property_guide.get("required", []) + property_guide.get(
        "recommended", []
    )
    if not prop_candidates:
        prop_candidates = property_guide.get("schema", [])
    for prop in prop_candidates:
        base = prop.split(".", 1)[0]
        for range_type in prop_ranges.get(base, set()):
            if range_type == "Thing":
                continue
            related.add(range_type)
    return sorted(related)


def property_guides_with_related(
    type_name: str,
    max_depth: int = 2,
) -> dict[str, dict[str, list[str]]]:
    type_name = normalize_type(type_name)
    ranges = _schema_property_ranges()
    guides: dict[str, dict[str, list[str]]] = {}
    queue: list[tuple[str, int]] = [(type_name, 0)]
    seen: set[str] = set()

    while queue:
        current, depth = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        guide = _property_guide_for_type(current)
        guides[current] = guide
        if depth >= max_depth:
            continue
        for related in _related_types_for_type(current, guide, ranges):
            if related not in seen:
                queue.append((related, depth + 1))

    return guides


def shape_specs_for_type(type_name: str) -> list[str]:
    return all_shape_specs()


def shape_specs_for_types(type_names: list[str]) -> list[str]:
    return all_shape_specs()


def all_shape_specs() -> list[str]:
    shapes_dir = resources.files("wordlift_sdk.validation.shacls")
    shape_specs: list[str] = []
    for entry in shapes_dir.iterdir():
        if not entry.is_file() or not entry.name.endswith(".ttl"):
            continue
        if entry.name not in shape_specs:
            shape_specs.append(entry.name)
    if "schemaorg-grammar.ttl" not in shape_specs:
        shape_specs.append("schemaorg-grammar.ttl")
    return shape_specs


def _slugify(value: str, default: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().lower()).strip("-")
    return cleaned or default


def _dash_type(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "-", value.strip())
    value = re.sub(r"(?<!^)(?=[A-Z])", "-", value)
    return re.sub(r"-+", "-", value).strip("-").lower()


def _pluralize(value: str) -> str:
    if value.endswith("y") and len(value) > 1 and value[-2] not in "aeiou":
        return value[:-1] + "ies"
    if value.endswith(("s", "x", "z", "ch", "sh")):
        return value + "es"
    return value + "s"


def _hash_url(url: str, length: int = 12) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:length]


def build_output_basename(url: str, default: str = "page") -> str:
    parsed = urlparse(url)
    base = f"{parsed.netloc}{parsed.path}".strip("/")
    slug = _slugify(base or url, default=default)
    return f"{slug}--{_hash_url(url)}"


def build_id(
    dataset_uri: str,
    type_name: str,
    name: str,
    url: str | None,
    index: int,
) -> str:
    return build_id_base(dataset_uri, type_name, name, url, index)


def build_id_base(
    base_uri: str,
    type_name: str,
    name: str,
    url: str | None,
    index: int,
) -> str:
    base = base_uri.rstrip("/")
    dashed_type = _dash_type(type_name)
    plural_type = _pluralize(dashed_type)
    name_slug = _slugify(name, default=_dash_type(type_name))
    if url:
        suffix = _hash_url(url)
    else:
        suffix = str(index)
    return f"{base}/{plural_type}/{name_slug}-{suffix}"


def _format_prop_list(items: list[str]) -> str:
    if not items:
        return "none"
    return ", ".join(items)


def _agent_prompt(
    url: str,
    html: str,
    target_type: str | None,
    property_guides: dict[str, dict[str, list[str]]] | None = None,
    missing_required: list[str] | None = None,
    missing_recommended: list[str] | None = None,
    previous_yarrml: str | None = None,
    validation_errors: list[str] | None = None,
    validation_report: list[str] | None = None,
    xpath_warnings: list[str] | None = None,
    allow_properties: dict[str, list[str]] | None = None,
    quality_feedback: list[str] | None = None,
) -> str:
    target = target_type or "AUTO"
    guide_lines: list[str] = []
    if property_guides:
        guide_lines.append(
            "Property guide by type (Google required/recommended + Schema.org grammar):"
        )
        for type_name, guide in property_guides.items():
            guide_lines.append(f"- {type_name}:")
            guide_lines.append(
                f"  - Required (Google): {_format_prop_list(guide.get('required', []))}"
            )
            guide_lines.append(
                f"  - Recommended (Google): {_format_prop_list(guide.get('recommended', []))}"
            )
            guide_lines.append(
                "  - Optional (Schema.org, excluding required/recommended): "
                f"{_format_prop_list(guide.get('optional', []))}"
            )
            guide_lines.append(
                f"  - All Schema.org properties for {type_name}: {_format_prop_list(guide.get('schema', []))}"
            )
        guide_lines.append("")
        guide_lines.append(
            "If a required property is not present on the page, omit it (do not fabricate)."
        )
        guide_lines.append("Only use properties listed in the guide for each type.")
        guide_lines.append("")
    if allow_properties:
        guide_lines.append("Allowed properties (Google only):")
        for type_name, props in allow_properties.items():
            guide_lines.append(f"- {type_name}: {_format_prop_list(props)}")
        guide_lines.append("")

    refine_lines: list[str] = []
    if missing_required:
        refine_lines.append("Missing required properties in the previous mapping:")
        refine_lines.append(", ".join(missing_required))
        refine_lines.append(
            "Update the mapping to add these properties if the data exists on the page."
        )
        refine_lines.append("Keep existing correct mappings and selectors.")
        refine_lines.append("")
    if missing_recommended:
        refine_lines.append("Missing recommended properties in the previous mapping:")
        refine_lines.append(", ".join(missing_recommended))
        refine_lines.append("Add these properties if the data exists on the page.")
        refine_lines.append("")
    if validation_errors:
        refine_lines.append("Validation errors from the previous mapping:")
        refine_lines.extend(validation_errors)
        refine_lines.append("Fix these issues without fabricating data.")
        refine_lines.append("")
    if validation_report:
        refine_lines.append("Validation report from the previous mapping:")
        refine_lines.extend(validation_report)
        refine_lines.append(
            "Use the report to fix the mapping without fabricating data."
        )
        refine_lines.append("")
    if xpath_warnings:
        refine_lines.append("XPath evaluation warnings from the previous mapping:")
        refine_lines.extend(xpath_warnings)
        refine_lines.append("Fix the XPath selectors that returned no results.")
        refine_lines.append("")
    if quality_feedback:
        refine_lines.append("Quality feedback from the previous mapping:")
        refine_lines.extend(quality_feedback)
        refine_lines.append(
            "Improve the mapping to raise the quality score while only using data present in XHTML."
        )
        refine_lines.append("")
    if previous_yarrml:
        refine_lines.append("Previous mapping:")
        refine_lines.append(previous_yarrml.strip())
        refine_lines.append("")

    guide_text = "\n".join(guide_lines) if guide_lines else ""
    refine_text = "\n".join(refine_lines) if refine_lines else ""
    return (
        f"analyze the entities on this webpage: {url}\n"
        "\n"
        "You are a structured data extraction agent.\n"
        "Goal: produce a YARRRML mapping using XPath only.\n"
        "Use the provided XHTML source instead of fetching the URL.\n"
        "Do NOT parse any existing structured data (JSON-LD, RDFa, Microdata).\n"
        "Do NOT emit @id values. IDs will be assigned locally.\n"
        "Output ONLY the YARRRML mapping (no prose, no code fences).\n"
        "\n"
        f"Target Schema.org type: {target}\n"
        "\n"
        "Requirements:\n"
        "- Use XPath in all selectors.\n"
        "- Use $(xpath) for XPath references (not {xpath}).\n"
        '- Do NOT wrap XPath expressions in quotes inside $(...). Use $(/path), not $("/path").\n'
        '- Always quote attribute values in XPath (e.g., @id="..."). Do NOT use @id=foo.\n'
        "- The main mapping must include schema:url with the exact URL.\n"
        "- Always include schema:name for every mapped node.\n"
        "- Include schema:description for Review if available.\n"
        "- Include schema:image if available (prefer og:image). \n"
        "- Include schema:inLanguage if available (html/@lang). \n"
        "- Include schema:publisher if available (prefer og:site_name as Organization). \n"
        "- Include schema:reviewBody for Review if available (main article text). Prefer the paragraph immediately following the H1\n"
        "  (e.g., following-sibling::p[1]) and only use class-based selectors if necessary.\n"
        '- Include schema:datePublished for Review if available (time/@datetime or meta[property="article:published_time"],\n'
        "  otherwise use the first byline date).\n"
        "- Include positiveNotes/negativeNotes for Review if available.\n"
        "- Include relevant properties for the main type.\n"
        "- If Target Schema.org type is AUTO, infer the best type and use it.\n"
        "- Define dependent nodes as separate mappings and link them from the main mapping.\n"
        "- Prefer reusable XPath selectors that generalize across pages using the same template.\n"
        "- Avoid brittle selectors that depend on full class names, IDs, or numeric suffixes unless there is no alternative.\n"
        "- Prefer structural paths (head/meta, main/h1, time[@datetime], link[@rel], figure/img) and stable attributes.\n"
        "- If you must use classes or IDs, prefer contains(@class, 'stable-token') over exact matches and avoid numeric IDs.\n"
        "- NEVER use table IDs with numeric suffixes (e.g., tablepress-12345). Instead, locate tables by header text\n"
        "  (e.g., th contains 'APR'/'rating') and then select the adjacent cell by position or data-th.\n"
        '- Do NOT key selectors off a specific person name or URL slug; use byline labels like "Written by" or metadata instead.\n'
        "- For author, prefer metadata or rel links first (meta[name=author], meta[property=article:author], link[rel=author]) before class-based selectors.\n"
        '- If the page shows a byline label (e.g., "Written by"), select the author link or text immediately following that label.\n'
        "- For positiveNotes/negativeNotes (Review/Product and subclasses only), anchor on semantic headings (Pros/Cons, Advantages/Disadvantages,\n"
        "  What we like/What we don't like). Prefer heading text matches (contains(., 'Pros')) over IDs/classes,\n"
        "  and select the closest following list items (li) from ul/ol, rows from tables, or terms/defs from dl.\n"
        "  Detect the page language and include localized heading variants with English as a fallback. Avoid site-specific classes/IDs unless there is no alternative.\n"
        "- Only include reviewRating if the page explicitly provides a rating score (stars or numeric rating). Do NOT infer ratings from APR/fee tables or unrelated metrics.\n"
        "- Do NOT use hard-coded literal values. All values must come from XPath except schema:url.\n"
        "- ratingValue must be a literal extracted from XPath (not an IRI).\n"
        "- reviewRating must point to a Rating node.\n"
        "- author must be a Person or Organization node.\n"
        "\n"
        f"{guide_text}"
        f"{refine_text}"
        "XHTML:\n"
        f"{html}\n"
    )


def _quality_prompt(
    url: str,
    xhtml: str,
    jsonld: dict[str, Any] | list[Any],
    property_guides: dict[str, dict[str, list[str]]] | None,
    target_type: str | None,
) -> str:
    guide_lines: list[str] = []
    if property_guides:
        guide_lines.append(
            "Property guide by type (Google required/recommended + Schema.org grammar):"
        )
        for type_name, guide in property_guides.items():
            guide_lines.append(f"- {type_name}:")
            guide_lines.append(
                f"  - Required (Google): {_format_prop_list(guide.get('required', []))}"
            )
            guide_lines.append(
                f"  - Recommended (Google): {_format_prop_list(guide.get('recommended', []))}"
            )
            guide_lines.append(
                "  - Optional (Schema.org, excluding required/recommended): "
                f"{_format_prop_list(guide.get('optional', []))}"
            )
        guide_lines.append("")
    guide_text = "\n".join(guide_lines) if guide_lines else ""
    payload = json.dumps(jsonld, ensure_ascii=True)
    return (
        f"analyze the entities on this webpage: {url}\n"
        "\n"
        "You are evaluating structured data quality.\n"
        "Compare the XHTML and JSON-LD. Only count properties that are present in XHTML.\n"
        "Do NOT penalize missing properties if they do not appear in the XHTML.\n"
        "Return a JSON object with keys: score (0-10 integer), missing_in_jsonld (list),\n"
        "suggested_xpath (object mapping property -> XPath), notes (list).\n"
        "Use XPath in suggested_xpath and keep it generic/reusable.\n"
        "\n"
        f"Target Schema.org type: {target_type or 'AUTO'}\n"
        "\n"
        f"{guide_text}"
        "XHTML:\n"
        f"{xhtml}\n"
        "\n"
        "JSON-LD:\n"
        f"{payload}\n"
    )


async def _ask_agent_async(
    prompt: str, api_key: str, model: str | None = None
) -> object:
    async with _build_agent_client(api_key) as api_client:
        api = AgentApi(api_client)
        ask_request = AskRequest(message=prompt, model=model or _AGENT_MODEL)
        return await api.ask_request_api_ask_post(ask_request)


def _collect_strings(payload: Any, results: list[str]) -> None:
    if isinstance(payload, str):
        if payload.strip():
            results.append(payload)
        return
    if isinstance(payload, dict):
        for value in payload.values():
            _collect_strings(value, results)
        return
    if isinstance(payload, list):
        for value in payload:
            _collect_strings(value, results)


def _extract_agent_text(payload: Any) -> str | None:
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    if isinstance(payload, dict):
        for key in (
            "response",
            "answer",
            "content",
            "result",
            "output",
            "text",
            "message",
        ):
            if key in payload:
                value = _extract_agent_text(payload.get(key))
                if value:
                    return value
    strings: list[str] = []
    _collect_strings(payload, strings)
    for value in strings:
        if "mappings:" in value or "prefixes:" in value:
            return value.strip()
    for value in strings:
        if value.strip():
            return value.strip()
    return None


def _extract_agent_json(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        return payload
    text = _extract_agent_text(payload)
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    snippet = text[start : end + 1]
    try:
        return json.loads(snippet)
    except Exception:
        return None


def ask_agent_for_yarrml(
    api_key: str,
    url: str,
    html: str,
    target_type: str | None,
    debug: bool = False,
    debug_path: Path | None = None,
    property_guides: dict[str, dict[str, list[str]]] | None = None,
    missing_required: list[str] | None = None,
    missing_recommended: list[str] | None = None,
    previous_yarrml: str | None = None,
    validation_errors: list[str] | None = None,
    validation_report: list[str] | None = None,
    xpath_warnings: list[str] | None = None,
    allow_properties: dict[str, list[str]] | None = None,
    quality_feedback: list[str] | None = None,
) -> str:
    prompt = _agent_prompt(
        url,
        html,
        target_type,
        property_guides=property_guides,
        missing_required=missing_required,
        missing_recommended=missing_recommended,
        previous_yarrml=previous_yarrml,
        validation_errors=validation_errors,
        validation_report=validation_report,
        xpath_warnings=xpath_warnings,
        allow_properties=allow_properties,
        quality_feedback=quality_feedback,
    )
    try:
        response = asyncio.run(_ask_agent_async(prompt, api_key))
    except Exception as exc:
        raise RuntimeError(f"Agent request failed: {exc}") from exc

    if isinstance(response, dict):
        data = response
    else:
        try:
            data = response.model_dump()
        except Exception:
            data = {}

    if debug and debug_path is not None:
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_payload = {
            "prompt": prompt,
            "response": data,
        }
        debug_path.write_text(json.dumps(debug_payload, indent=2))

    extracted = _extract_agent_text(data)
    if extracted:
        return extracted

    raise RuntimeError("Agent response did not include YARRRML content.")


def ask_agent_for_quality(
    api_key: str,
    url: str,
    xhtml: str,
    jsonld: dict[str, Any] | list[Any],
    property_guides: dict[str, dict[str, list[str]]] | None,
    target_type: str | None,
) -> dict[str, Any] | None:
    prompt = _quality_prompt(url, xhtml, jsonld, property_guides, target_type)
    try:
        response = asyncio.run(_ask_agent_async(prompt, api_key))
    except Exception as exc:
        raise RuntimeError(f"Agent quality request failed: {exc}") from exc
    return _extract_agent_json(response)


def _replace_sources_with_file(yarrml: str, file_uri: str) -> str:
    pattern = re.compile(r"(\[\s*['\"])([^'\"]+)(['\"]\s*,\s*['\"]xpath['\"])")
    inline_pattern = re.compile(r"(\[\s*)([^,\]]+?~xpath)(\s*,)")

    def repl(match: re.Match[str]) -> str:
        return f"{match.group(1)}{file_uri}{match.group(3)}"

    def repl_inline(match: re.Match[str]) -> str:
        return f"{match.group(1)}{file_uri}~xpath{match.group(3)}"

    yarrml = pattern.sub(repl, yarrml)
    return inline_pattern.sub(repl_inline, yarrml)


def _replace_sources_with_placeholder(yarrml: str, placeholder: str) -> str:
    pattern = re.compile(r"(\[\s*['\"])([^'\"]+)(['\"]\s*,\s*['\"]xpath['\"])")
    inline_pattern = re.compile(r"(\[\s*)([^,\]]+?~xpath)(\s*,)")

    def repl(match: re.Match[str]) -> str:
        return f"{match.group(1)}{placeholder}{match.group(3)}"

    def repl_inline(match: re.Match[str]) -> str:
        return f"{match.group(1)}{placeholder}~xpath{match.group(3)}"

    yarrml = pattern.sub(repl, yarrml)
    return inline_pattern.sub(repl_inline, yarrml)


def make_reusable_yarrrml(
    yarrml: str, url: str, source_placeholder: str = "__XHTML__"
) -> str:
    normalized = _replace_sources_with_placeholder(yarrml, source_placeholder)
    escaped_url = re.escape(url)
    normalized = re.sub(
        rf"(schema:url\s*,\s*['\"])({escaped_url})(['\"])",
        r"\1__URL__\3",
        normalized,
    )
    return normalized


def _strip_quotes(value: str | None) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def _strip_wrapped_list(value: str | None) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1].strip()
    return _strip_quotes(value)


def _strip_all_quotes(value: str | None) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip()
    while (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1].strip()
    return value


def _normalize_xpath_literal(value: str) -> str:
    value = value.strip()
    if value.startswith("{") and value.endswith("}"):
        inner = value[1:-1].strip()
        return f"$({inner})"
    if value.startswith("$(xpath)/"):
        tail = value[len("$(xpath)") :]
        return f"$({tail})"
    if value.startswith("$(xpath://") or value.startswith("$(xpath:/"):
        tail = value[len("$(xpath:") :]
        return f"$({tail})"
    if value.startswith("$(") and value.endswith(")"):
        inner = value[2:-1].strip()
        if (inner.startswith('"') and inner.endswith('"')) or (
            inner.startswith("'") and inner.endswith("'")
        ):
            return f"$({inner[1:-1]})"
    if value.startswith("$(xpath)',"):
        _, _, tail = value.partition(",")
        tail = _strip_all_quotes(tail.strip())
        return _normalize_xpath_literal(f"$({tail})")
    return value


def _looks_like_xpath(value: str) -> bool:
    value = value.strip()
    return (
        (value.startswith("$(") and value.endswith(")"))
        or value.startswith("/")
        or value.startswith(".//")
        or value.startswith("//")
        or value.startswith("normalize-")
        or value.startswith("normalize(")
        or value.startswith("string(")
        or value.startswith("concat(")
    )


def _simplify_xpath(value: str) -> str:
    value = value.strip()
    if value.startswith("$(") and value.endswith(")"):
        value = value[2:-1].strip()
        if value.startswith("xpath="):
            value = value[len("xpath=") :].strip()
        if value.startswith("xpath://") or value.startswith("xpath:/"):
            value = value[len("xpath:") :]
    if value.startswith(('"', "'")) and value.endswith(('"', "'")) and len(value) >= 2:
        value = value[1:-1]
    value = value.replace('\\"', '"').replace("\\'", "'")
    match = re.match(r"(?:normalize-space|string)\((.+)\)$", value)
    if match:
        return match.group(1).strip()
    return value


def _normalize_xpath_reference(value: str) -> str:
    value = value.strip()
    value = value.replace("/text()", "")
    value = value.replace("text()", "")
    value = re.sub(r"contains\(@class,\s*\"([^\"]+)\"\)", r"@class=\"\1\"", value)
    value = re.sub(r"contains\(@class,\s*'([^']+)'\)", r"@class=\"\1\"", value)
    value = re.sub(r"contains\(@id,\s*\"([^\"]+)\"\)", r"@id=\"\1\"", value)
    value = re.sub(r"contains\(@id,\s*'([^']+)'\)", r"@id=\"\1\"", value)
    return value


def _first_list_value(value: str) -> str:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        match = re.search(r"['\"]([^'\"]+)['\"]", value)
        if match:
            return match.group(1)
    return _strip_all_quotes(_strip_wrapped_list(value))


def _normalize_agent_yarrml(
    raw: str,
    url: str,
    file_uri: str,
    target_type: str | None,
) -> tuple[str, list[dict[str, Any]]]:
    raw = _quote_unquoted_xpath_attributes(raw)
    raw = re.sub(r"(['\"])\\{([^{}]+)\\}\\1", r"\\1$(\\2)\\1", raw)
    raw = re.sub(
        r"(['\"])\\$\\(xpath\\)\\1\\s*,\\s*(['\"])([^'\"]+)\\2", r"\\1$(\\3)\\1", raw
    )
    lines = raw.splitlines()
    mappings: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_mappings = False
    mappings_indent: int | None = None
    ignore_keys = {"mappings", "prefixes", "sources", "po"}
    last_p: str | None = None
    pending_o: str | None = None
    in_props_block = False
    props_indent = 0
    in_sources = False
    sources_indent: int | None = None

    for line in lines:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))
        if not stripped:
            continue
        if stripped == "mappings:":
            in_mappings = True
            mappings_indent = indent
            continue
        if (
            in_mappings
            and stripped.endswith(":")
            and not stripped.startswith("-")
            and not stripped.startswith("s:")
            and mappings_indent is not None
            and indent == mappings_indent + 2
        ):
            name = stripped[:-1].strip()
            if name in ignore_keys:
                continue
            current = {"name": name, "type": None, "props": []}
            mappings.append(current)
            last_p = None
            pending_o = None
            in_props_block = False
            continue
        if current is None:
            continue
        if stripped == "sources:":
            in_sources = True
            sources_indent = indent
            continue
        if in_sources:
            if sources_indent is not None and indent > sources_indent:
                continue
            in_sources = False
            sources_indent = None
        if stripped == "po:":
            continue
        if stripped == "p:":
            in_props_block = True
            props_indent = indent
            pending_o = None
            last_p = None
            continue
        if in_props_block and indent <= props_indent and stripped != "p:":
            in_props_block = False
            pending_o = None
        if stripped.startswith("- [") and "value:" in stripped:
            if current is None:
                continue
            match = re.search(r"value:\s*\"([^\"]+)\"", stripped) or re.search(
                r"value:\s*'([^']+)'", stripped
            )
            if match:
                current["source_xpath"] = match.group(1)
            else:
                match = re.search(r"\\['html'\\]\\s*,\\s*\"([^\"]+)\"", stripped)
                if match:
                    current["source_xpath"] = match.group(1)
            continue
        if stripped.startswith("- ["):
            if current is None:
                continue
            match = re.match(r"- \[\s*\"([^\"]+)\"\s*\]$", stripped) or re.match(
                r"- \[\s*'([^']+)'\s*\]$", stripped
            )
            if match:
                current["source_xpath"] = match.group(1)
                continue
        if stripped.startswith("s:") and stripped.endswith(":") and stripped != "s:":
            prop_name = stripped[2:-1].strip()
            if prop_name:
                pending_o = prop_name
            continue
        if stripped.startswith("s:") and not stripped.startswith("s: "):
            rest = stripped[2:]
            prop, _, obj_part = rest.partition(":")
            prop = prop.strip()
            obj = _normalize_xpath_literal(
                _strip_all_quotes(_strip_wrapped_list(obj_part.strip()))
            )
            if prop:
                current["props"].append((prop, obj))
            continue
        if stripped.startswith("s:"):
            value = _strip_all_quotes(
                _strip_wrapped_list(stripped.split(":", 1)[1].strip())
            )
            if value.startswith(("http://", "https://")) or _looks_like_xpath(value):
                continue
            if value.startswith("schema:"):
                current["type"] = normalize_type(value)
                continue
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9]+", value):
                current["type"] = value
            continue
        if stripped.startswith("- p:"):
            _, value = stripped.split("p:", 1)
            last_p = _strip_quotes(value.strip())
            pending_o = None
            continue
        if in_props_block and stripped.startswith("schema:") and stripped.endswith(":"):
            pending_o = stripped[:-1].strip()
            continue
        if stripped.startswith("o:") and last_p:
            _, value = stripped.split("o:", 1)
            obj = _normalize_xpath_literal(
                _strip_all_quotes(_strip_wrapped_list(value.strip()))
            )
            if obj:
                current["props"].append((last_p, obj))
                last_p = None
                pending_o = None
            else:
                pending_o = last_p
            continue
        if stripped.startswith("- [a,") or stripped.startswith("- [ a,"):
            match = re.search(r"'schema:([^']+)'", stripped) or re.search(
                r"\"schema:([^\"]+)\"", stripped
            )
            if match:
                current["type"] = normalize_type(match.group(1))
            continue
        if stripped.startswith("value:") and pending_o:
            _, value = stripped.split("value:", 1)
            obj = _normalize_xpath_literal(_first_list_value(value.strip()))
            current["props"].append((pending_o, obj))
            pending_o = None
            last_p = None
            continue
        if stripped.startswith("mapping:") and pending_o:
            _, value = stripped.split("mapping:", 1)
            obj = _normalize_xpath_literal(
                _strip_all_quotes(_strip_wrapped_list(value.strip()))
            )
            if obj:
                current["props"].append((pending_o, obj))
            pending_o = None
            last_p = None
            continue
        if stripped.startswith("- ["):
            if "p:" in stripped and "o:" in stripped:
                match = re.search(r"\[p:\s*([^,]+),\s*o:\s*(.+)\]$", stripped)
                if match:
                    prop = _strip_quotes(match.group(1).strip())
                    obj = _normalize_xpath_literal(
                        _strip_all_quotes(_strip_wrapped_list(match.group(2).strip()))
                    )
                    if prop == "a":
                        continue
                    current["props"].append((prop, obj))
                continue
            match = re.search(r"\[\s*([^,]+)\s*,\s*(.+)\]$", stripped)
            if match:
                prop = _strip_quotes(match.group(1).strip())
                obj = _normalize_xpath_literal(
                    _strip_all_quotes(_strip_wrapped_list(match.group(2).strip()))
                )
                if prop == "a":
                    continue
                current["props"].append((prop, obj))

    if not mappings:
        raise RuntimeError("Agent response did not include recognizable mappings.")

    mapping_names = {m["name"] for m in mappings}
    target = normalize_type(target_type) if target_type else None
    denied_props = {"schema:html", "html"}
    schema_props = _schema_property_set()

    main_mapping = None
    for mapping in mappings:
        if target and normalize_type(mapping["type"] or "") == target:
            main_mapping = mapping
            break
    if main_mapping is None:
        main_mapping = mappings[0]
    if main_mapping:
        main_mapping["__main__"] = True

    output_lines = [
        "prefixes:",
        f"  schema: '{_SCHEMA_BASE}/'",
        "  ex: 'http://example.com/'",
        "mappings:",
    ]

    for mapping in mappings:
        map_name = mapping["name"]
        map_type = mapping["type"] or ("Review" if mapping is main_mapping else "Thing")
        map_type = normalize_type(map_type)
        output_lines += [
            f"  {map_name}:",
            "    sources:",
            f"      - [{file_uri}~xpath, '/']",
            f"    s: ex:{map_name}~iri",
            "    po:",
            f"      - [a, 'schema:{map_type}']",
        ]
        props = list(mapping["props"])
        source_xpath = mapping.get("source_xpath")

        if mapping is main_mapping:
            has_url = any(p == "schema:url" for p, _ in props)
            if not has_url:
                props.insert(0, ("schema:url", url))

        for prop, obj in props:
            if not prop.startswith("schema:"):
                prop = f"schema:{prop}"
            prop_name = prop[7:]
            if prop_name == "a" or prop == "schema:a":
                continue
            if "~" in prop_name or "http" in prop_name:
                continue
            if prop in denied_props:
                continue
            if prop_name not in schema_props:
                continue
            if not obj:
                continue
            if obj == "{value}" and source_xpath:
                obj = source_xpath
            if (
                isinstance(obj, str)
                and obj.startswith("ex:")
                and obj[3:] in mapping_names
            ):
                obj = obj[3:]
            if obj in mapping_names:
                output_lines.append(f"      - [{prop}, ex:{obj}~iri]")
                continue
            if _looks_like_xpath(obj):
                xpath = _normalize_xpath_reference(_simplify_xpath(obj)).replace(
                    "'", '"'
                )
                output_lines.append(f"      - [{prop}, '$(%s)']" % xpath)
                continue
            output_lines.append(f"      - [{prop}, '{obj}']")

    return "\n".join(output_lines) + "\n", mappings


def _quote_unquoted_xpath_attributes(text: str) -> str:
    pattern = re.compile(
        r"@(id|class|property|rel|name|type|itemprop|content|href|src)\s*=\s*([A-Za-z0-9_-]+)"
    )

    def repl(match: re.Match[str]) -> str:
        attr = match.group(1)
        value = match.group(2)
        return f'@{attr}="{value}"'

    return pattern.sub(repl, text)


def _run_yarrrml_parser(input_path: Path, output_path: Path) -> None:
    parser = shutil.which("yarrrml-parser")
    if not parser:
        raise RuntimeError(
            "yarrrml-parser is required. Install with: npm install -g @rmlio/yarrrml-parser"
        )
    if output_path.exists():
        output_path.unlink()
    result = subprocess.run(
        [parser, "-i", str(input_path), "-o", str(output_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if not output_path.exists():
        error = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"yarrrml-parser failed to produce output. {error}")
    if result.returncode != 0:
        raise RuntimeError(f"yarrrml-parser failed: {result.stderr.strip()}")


def _materialize_graph(mapping_path: Path) -> Graph:
    try:
        import morph_kgc
    except ImportError as exc:
        raise RuntimeError(
            "morph-kgc is required. Install with: pip install morph-kgc"
        ) from exc

    config = (
        "[CONFIGURATION]\n"
        "output_format = N-TRIPLES\n"
        "\n"
        "[DataSource1]\n"
        f"mappings = {mapping_path}\n"
    )
    return morph_kgc.materialize(config)


def materialize_yarrrml(
    yarrrml: str,
    xhtml_path: Path,
    workdir: Path,
    *,
    url: str | None = None,
) -> Graph:
    file_uri = xhtml_path.as_posix()
    normalized = _replace_sources_with_file(yarrrml, file_uri)
    if url:
        normalized = re.sub(
            r"(schema:url\s*,\s*['\"])__URL__(['\"])",
            rf"\1{url}\2",
            normalized,
        )
    workdir.mkdir(parents=True, exist_ok=True)
    yarrml_path = workdir / "mapping.yarrrml"
    rml_path = workdir / "mapping.ttl"
    yarrml_path.write_text(normalized)
    _run_yarrrml_parser(yarrml_path, rml_path)
    _ensure_subject_termtype_iri(rml_path)
    _normalize_reference_formulation(rml_path)
    return _materialize_graph(rml_path)


def normalize_yarrrml_mappings(
    yarrrml: str,
    url: str,
    xhtml_path: Path,
    target_type: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    return _normalize_agent_yarrml(yarrrml, url, xhtml_path.as_posix(), target_type)


def materialize_yarrrml_jsonld(
    yarrrml: str,
    xhtml_path: Path,
    workdir: Path,
    *,
    url: str | None = None,
) -> dict[str, Any] | list[Any]:
    file_uri = xhtml_path.as_posix()
    normalized = _replace_sources_with_file(yarrrml, file_uri)
    if url:
        normalized = re.sub(
            r"(schema:url\s*,\s*['\"])__URL__(['\"])",
            rf"\1{url}\2",
            normalized,
        )
    workdir.mkdir(parents=True, exist_ok=True)
    yarrml_path = workdir / "mapping.yarrml"
    rml_path = workdir / "mapping.ttl"
    yarrml_path.write_text(normalized)
    _run_yarrrml_parser(yarrml_path, rml_path)
    _ensure_subject_termtype_iri(rml_path)
    _normalize_reference_formulation(rml_path)
    return _materialize_jsonld(rml_path)


def postprocess_jsonld(
    jsonld_raw: dict[str, Any] | list[Any],
    mappings: list[dict[str, Any]],
    xhtml: str,
    dataset_uri: str,
    url: str,
    target_type: str | None = None,
) -> dict[str, Any]:
    jsonld_raw = _fill_jsonld_from_mappings(jsonld_raw, mappings, xhtml)
    _ensure_node_ids(jsonld_raw, dataset_uri, url)
    _dedupe_review_notes(jsonld_raw)
    normalized = normalize_jsonld(
        jsonld_raw, dataset_uri, url, target_type, embed_nodes=False
    )
    _materialize_literal_nodes(normalized, dataset_uri, url)
    _ensure_author_name(normalized, xhtml, dataset_uri, url)
    _ensure_review_url(normalized, url)
    _prune_empty_rating_nodes(normalized)
    return normalized


def _prune_empty_rating_nodes(data: dict[str, Any] | list[Any]) -> None:
    nodes = _flatten_jsonld(data)
    if not nodes:
        return
    rating_value_key = f"{_SCHEMA_BASE}/ratingValue"
    empty_rating_ids: set[str] = set()

    def _has_rating_value(node: dict[str, Any]) -> bool:
        value = node.get(rating_value_key, node.get("ratingValue"))
        if value is None:
            return False
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, dict):
                text = item.get("@value") or item.get("value")
            else:
                text = item
            if isinstance(text, str) and text.strip():
                return True
            if isinstance(text, (int, float)):
                return True
        return False

    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_types = {
            normalize_type(t) for t in node.get("@type", []) if isinstance(t, str)
        }
        if "Rating" not in node_types:
            continue
        if not _has_rating_value(node):
            node_id = node.get("@id")
            if isinstance(node_id, str):
                empty_rating_ids.add(node_id)
    if not empty_rating_ids:
        return

    def _filter_refs(values: Any) -> Any:
        if isinstance(values, list):
            filtered = [
                value
                for value in values
                if not (
                    isinstance(value, dict) and value.get("@id") in empty_rating_ids
                )
            ]
            return filtered
        return values

    for node in nodes:
        if not isinstance(node, dict):
            continue
        for key in (f"{_SCHEMA_BASE}/reviewRating", "reviewRating"):
            if key in node:
                node[key] = _filter_refs(node[key])
                if not node[key]:
                    node.pop(key, None)

    if isinstance(data, dict) and isinstance(data.get("@graph"), list):
        data["@graph"] = [
            node
            for node in data["@graph"]
            if not (isinstance(node, dict) and node.get("@id") in empty_rating_ids)
        ]
    elif isinstance(data, list):
        data[:] = [
            node
            for node in data
            if not (isinstance(node, dict) and node.get("@id") in empty_rating_ids)
        ]


def _dedupe_review_notes(data: dict[str, Any] | list[Any]) -> None:
    nodes = _flatten_jsonld(data)
    if not nodes:
        return
    pos_key = f"{_SCHEMA_BASE}/positiveNotes"
    neg_key = f"{_SCHEMA_BASE}/negativeNotes"

    def _extract_values(values: Any) -> list[str]:
        if isinstance(values, list):
            items = values
        else:
            items = [values]
        normalized: list[str] = []
        for item in items:
            if isinstance(item, dict):
                value = item.get("@value") or item.get("value")
            else:
                value = item
            if isinstance(value, str):
                normalized.append(value.strip())
        return [value for value in normalized if value]

    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_types = {
            normalize_type(t) for t in node.get("@type", []) if isinstance(t, str)
        }
        if "Review" not in node_types and "Product" not in node_types:
            continue
        pos_values = _extract_values(node.get(pos_key) or node.get("positiveNotes"))
        neg_values = _extract_values(node.get(neg_key) or node.get("negativeNotes"))
        if pos_values and neg_values and pos_values == neg_values:
            node.pop(pos_key, None)
            node.pop("positiveNotes", None)


def _materialize_literal_nodes(
    data: dict[str, Any] | list[Any],
    dataset_uri: str,
    url: str,
) -> None:
    nodes = _flatten_jsonld(data)
    if not nodes:
        return
    graph = data.get("@graph") if isinstance(data, dict) else None
    if not isinstance(graph, list):
        return
    schema_author = f"{_SCHEMA_BASE}/author"
    schema_item = f"{_SCHEMA_BASE}/itemReviewed"
    schema_publisher = f"{_SCHEMA_BASE}/publisher"
    schema_name = f"{_SCHEMA_BASE}/name"

    def _ensure_node(type_name: str, name: str, index: int) -> dict[str, Any]:
        node_id = build_id_base(dataset_uri, type_name, name, url, index)
        node = {
            "@id": node_id,
            "@type": [f"{_SCHEMA_BASE}/{type_name}"],
            schema_name: [{"@value": name}],
            "@context": _SCHEMA_BASE,
        }
        graph.append(node)
        return node

    def _replace_literal(
        node: dict[str, Any], key: str, type_name: str, start_index: int
    ) -> None:
        values = node.get(key)
        if not values:
            return
        items = values if isinstance(values, list) else [values]
        new_refs: list[dict[str, Any]] = []
        for idx, item in enumerate(items, start=start_index):
            if isinstance(item, dict) and item.get("@id"):
                new_refs.append(item)
                continue
            if isinstance(item, dict) and "@value" in item:
                name = str(item["@value"]).strip()
            else:
                name = str(item).strip()
            if not name:
                continue
            new_node = _ensure_node(type_name, name, idx)
            new_refs.append({"@id": new_node["@id"]})
        if new_refs:
            node[key] = new_refs
        else:
            node.pop(key, None)

    review_nodes = [
        node
        for node in nodes
        if isinstance(node, dict)
        and "Review"
        in {normalize_type(t) for t in node.get("@type", []) if isinstance(t, str)}
    ]
    for index, review in enumerate(review_nodes, start=1):
        _replace_literal(review, schema_author, "Person", index)
        _replace_literal(review, schema_item, "Product", index + 100)
        _replace_literal(review, schema_publisher, "Organization", index + 200)


def _ensure_review_url(data: dict[str, Any] | list[Any], url: str) -> None:
    nodes = _flatten_jsonld(data)
    if not nodes or not url:
        return
    url_key = f"{_SCHEMA_BASE}/url"
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_types = {
            normalize_type(t) for t in node.get("@type", []) if isinstance(t, str)
        }
        if "Review" not in node_types:
            continue
        if url_key not in node:
            node[url_key] = [{"@value": url}]


def _ensure_author_name(
    data: dict[str, Any] | list[Any],
    xhtml: str,
    dataset_uri: str,
    url: str,
) -> None:
    author_name = _extract_author_name(xhtml)
    if not author_name:
        return
    nodes = _flatten_jsonld(data)
    if not nodes:
        return
    schema_name = f"{_SCHEMA_BASE}/name"
    schema_author = f"{_SCHEMA_BASE}/author"
    graph = data.get("@graph") if isinstance(data, dict) else None
    if not isinstance(graph, list):
        return

    author_nodes = [
        node
        for node in nodes
        if isinstance(node, dict)
        and "Person"
        in {normalize_type(t) for t in node.get("@type", []) if isinstance(t, str)}
    ]
    for node in author_nodes:
        if schema_name not in node:
            node[schema_name] = [{"@value": author_name}]

    review_nodes = [
        node
        for node in nodes
        if isinstance(node, dict)
        and "Review"
        in {normalize_type(t) for t in node.get("@type", []) if isinstance(t, str)}
    ]
    for review in review_nodes:
        if schema_author in review:
            continue
        author_node = build_id_base(dataset_uri, "Person", author_name, url, 0)
        graph.append(
            {
                "@id": author_node,
                "@type": [f"{_SCHEMA_BASE}/Person"],
                schema_name: [{"@value": author_name}],
                "@context": _SCHEMA_BASE,
            }
        )
        review[schema_author] = [{"@id": author_node}]


def _extract_author_name(xhtml: str) -> str | None:
    try:
        from lxml import html as lxml_html
    except Exception:
        return None
    parser = lxml_html.HTMLParser(encoding="utf-8", recover=True)
    try:
        doc = lxml_html.document_fromstring(xhtml, parser=parser)
    except Exception:
        return None

    candidates = [
        "//meta[@name='author']/@content",
        "//meta[@property='article:author']/@content",
        "//a[@rel='author']/text()",
        "//*[contains(normalize-space(.), 'Written by')]/following::a[1]/text()",
    ]
    for path in candidates:
        try:
            results = doc.xpath(path)
        except Exception:
            continue
        for value in results:
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _materialize_jsonld(mapping_path: Path) -> dict[str, Any] | list[Any]:
    graph = _materialize_graph(mapping_path)
    jsonld_str = graph.serialize(format="json-ld")
    return json.loads(jsonld_str)


def _ensure_subject_termtype_iri(mapping_path: Path) -> None:
    graph = Graph()
    graph.parse(mapping_path, format="turtle")
    for subject_map in graph.subjects(RDF.type, _RR.SubjectMap):
        graph.add((subject_map, _RR.termType, _RR.IRI))
    graph.serialize(destination=str(mapping_path), format="turtle")


def _normalize_reference_formulation(mapping_path: Path) -> None:
    graph = Graph()
    graph.parse(mapping_path, format="turtle")
    replaced = False
    for predicate in (_RML.referenceFormulation, _RML_LEGACY.referenceFormulation):
        for subject in list(graph.subjects(predicate, _QL.XPath)):
            graph.remove((subject, predicate, _QL.XPath))
            graph.add((subject, predicate, _RML.XPath))
            replaced = True
    if replaced:
        graph.serialize(destination=str(mapping_path), format="turtle")


def _flatten_jsonld(data: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [node for node in data if isinstance(node, dict)]
    if "@graph" in data and isinstance(data["@graph"], list):
        return [node for node in data["@graph"] if isinstance(node, dict)]
    return [data] if isinstance(data, dict) else []


def ensure_no_blank_nodes(graph: Graph) -> None:
    offenders: list[tuple[Identifier, Identifier, Identifier]] = []
    for subj, pred, obj in graph:
        if isinstance(subj, BNode) or isinstance(obj, BNode):
            offenders.append((subj, pred, obj))
            if len(offenders) >= 5:
                break
    if offenders:
        sample = "; ".join(f"{s} {p} {o}" for s, p, o in offenders)
        raise RuntimeError(
            "Blank nodes are not allowed in RDF output. "
            f"Found {len(offenders)} sample triples with blank nodes: {sample}"
        )


def _collect_jsonld_nodes(data: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            if _is_jsonld_node(value):
                nodes.append(value)
            for child in value.values():
                _walk(child)
        elif isinstance(value, list):
            for item in value:
                _walk(item)

    _walk(data)
    return nodes


def _strip_iri_suffix(value: str) -> str:
    return value[:-4] if value.endswith("~iri") else value


def _normalize_iri_suffixes(data: Any) -> Any:
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for key, value in data.items():
            if key == "@id" and isinstance(value, str):
                out[key] = _strip_iri_suffix(value)
            else:
                out[key] = _normalize_iri_suffixes(value)
        return out
    if isinstance(data, list):
        return [_normalize_iri_suffixes(item) for item in data]
    return data


def _xpath_first_text(doc: Any, xpath: str) -> str | None:
    def _eval(path: str) -> list[Any]:
        return doc.xpath(path)

    try:
        result = _eval(xpath)
    except Exception:
        return None
    if not result:
        relaxed = _relax_xpath(xpath)
        if relaxed != xpath:
            try:
                result = _eval(relaxed)
            except Exception:
                return None
        if not result:
            return None
    for item in result:
        if isinstance(item, str):
            text = item.strip()
        elif hasattr(item, "text_content"):
            text = item.text_content().strip()
        else:
            text = str(item).strip()
        if text:
            return text
    return None


def _relax_xpath(value: str) -> str:
    relaxed = value
    relaxed = re.sub(r"@class=\"([^\"]+)\"", r'contains(@class, "\1")', relaxed)
    relaxed = re.sub(r"@id=\"([^\"]+)\"", r'contains(@id, "\1")', relaxed)
    relaxed = relaxed.replace("//div[", "//*[")
    relaxed = relaxed.replace("/div[", "/*[")
    relaxed = relaxed.replace("//p[", "//*[")
    relaxed = relaxed.replace("/p[", "/*[")
    return relaxed


def _extract_list_items(doc: Any, xpaths: list[str]) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for path in xpaths:
        try:
            results = doc.xpath(path)
        except Exception:
            continue
        for item in results:
            if hasattr(item, "text_content"):
                text = item.text_content().strip()
            else:
                text = str(item).strip()
            if text:
                if text in seen:
                    continue
                seen.add(text)
                items.append(text)
    return items


def _build_item_list(items: list[str]) -> dict[str, Any]:
    entries = []
    for idx, name in enumerate(items, start=1):
        entries.append(
            {
                "@type": "ListItem",
                "position": idx,
                "name": name,
            }
        )
    return {"@type": "ItemList", "itemListElement": entries}


def _is_item_list_value(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    item = value[0]
    if not isinstance(item, dict):
        return False
    return normalize_type(item.get("@type")) == "ItemList"


def _extract_rating_number(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"-?\\d+(?:\\.\\d+)?", text)
    if not match:
        return None
    try:
        value = float(match.group(0))
    except ValueError:
        return None
    if value < 0 or value > 5:
        return None
    return match.group(0)


def _extract_rating_value(doc: Any) -> str | None:
    candidates = [
        "//*[@itemprop='ratingValue']/text()",
        "//*[@data-rating]/@data-rating",
        "//*[contains(@class, 'rating')]/text()",
        "//*[contains(@class, 'Rating')]/text()",
        "//*[contains(@id, 'rating')]/text()",
        "//*[contains(@id, 'Rating')]/text()",
        "//*[contains(@aria-label, 'rating')]/@aria-label",
        "//*[contains(@aria-label, 'star')]/@aria-label",
    ]
    for xpath in candidates:
        text = _xpath_first_text(doc, xpath)
        value = _extract_rating_number(text)
        if value is not None:
            return value
    return None


def enrich_graph_from_xhtml(graph: Graph, xhtml: str, url: str | None = None) -> None:
    try:
        from lxml import html as lxml_html
    except Exception:
        return
    parser = lxml_html.HTMLParser(encoding="utf-8", recover=True)
    try:
        doc = lxml_html.document_fromstring(xhtml, parser=parser)
    except Exception:
        return

    schema = Namespace(f"{_SCHEMA_BASE}/")
    review_type = URIRef(f"{_SCHEMA_BASE}/Review")
    review_nodes = list(graph.subjects(RDF.type, review_type))
    if not review_nodes:
        return

    title = (
        _xpath_first_text(doc, '/html/head/meta[@property="og:title"]/@content')
        or _xpath_first_text(doc, "/html/head/title/text()")
        or _xpath_first_text(doc, "//h1[1]")
    )
    description = _xpath_first_text(
        doc, '/html/head/meta[@property="og:description"]/@content'
    ) or _xpath_first_text(doc, '/html/head/meta[@name="description"]/@content')
    author_name = (
        _xpath_first_text(doc, '/html/head/meta[@name="author"]/@content')
        or _xpath_first_text(doc, '/html/head/meta[@property="author"]/@content')
        or _xpath_first_text(
            doc, '/html/head/meta[@property="article:author"]/@content'
        )
    )
    item_name = _xpath_first_text(doc, "//figure//img/@alt") or _xpath_first_text(
        doc, "//h1[1]"
    )

    for review in review_nodes:
        if url and graph.value(review, schema.url) is None:
            graph.add((review, schema.url, Literal(url)))
        if title and graph.value(review, schema.name) is None:
            graph.add((review, schema.name, Literal(title)))
        if description and graph.value(review, schema.description) is None:
            graph.add((review, schema.description, Literal(description)))

        author = graph.value(review, schema.author)
        if (
            author is not None
            and author_name
            and graph.value(author, schema.name) is None
        ):
            graph.add((author, schema.name, Literal(author_name)))

        item = graph.value(review, schema.itemReviewed)
        if item is not None and item_name and graph.value(item, schema.name) is None:
            graph.add((item, schema.name, Literal(item_name)))

        rating = graph.value(review, schema.reviewRating)
        if rating is not None and graph.value(rating, schema.ratingValue) is None:
            rating_value = _extract_rating_value(doc)
            if rating_value:
                graph.add((rating, schema.ratingValue, Literal(rating_value)))


def _fill_jsonld_from_mappings(
    data: dict[str, Any] | list[Any],
    mappings: list[dict[str, Any]],
    xhtml: str,
) -> dict[str, Any] | list[Any]:
    try:
        from lxml import html as lxml_html
    except Exception:
        return data
    parser = lxml_html.HTMLParser(encoding="utf-8", recover=True)
    try:
        doc = lxml_html.document_fromstring(xhtml, parser=parser)
    except Exception:
        return data

    nodes = _flatten_jsonld(data)
    node_by_id: dict[str, dict[str, Any]] = {
        str(node.get("@id")): node
        for node in nodes
        if isinstance(node, dict) and node.get("@id")
    }
    for node_id, node in list(node_by_id.items()):
        if node_id.endswith("~iri"):
            node_by_id.setdefault(node_id[: -len("~iri")], node)

    def _author_url_fallback() -> str | None:
        return _xpath_first_text(doc, "/html/head/link[@rel='author']/@href")

    author_url_fallback = _author_url_fallback()

    for mapping in mappings:
        name = mapping.get("name")
        if not name:
            continue
        node_id = f"http://example.com/{name}~iri"
        node = node_by_id.get(node_id) or node_by_id.get(f"http://example.com/{name}")
        if node is None:
            continue
        for prop, obj in mapping.get("props", []):
            prop_name = prop[7:] if prop.startswith("schema:") else prop
            if prop_name in {"a", "url"}:
                continue
            full_prop = f"{_SCHEMA_BASE}/{prop_name}"
            if full_prop in node:
                continue
            if not obj:
                continue
            if obj.startswith("ex:") and obj.endswith("~iri"):
                target = obj.split("ex:", 1)[1].split("~", 1)[0]
                node[full_prop] = [{"@id": f"http://example.com/{target}"}]
                continue
            if _looks_like_xpath(obj):
                xpath = _normalize_xpath_reference(_simplify_xpath(obj))
                text = _xpath_first_text(doc, xpath)
                if text:
                    if prop_name in {"ratingValue", "bestRating", "worstRating"}:
                        match = re.search(r"-?\\d+(?:\\.\\d+)?", text)
                        if not match:
                            continue
                        text = match.group(0)
                    node[full_prop] = [{"@value": text}]
                    if prop_name == "name":
                        node_type = node.get("@type") or []
                        node_types = {
                            normalize_type(t) for t in node_type if isinstance(t, str)
                        }
                        if node_types & {"Person", "Organization"}:
                            url_xpath = f"{xpath}/@href"
                            url_value = _xpath_first_text(doc, url_xpath)
                            if url_value:
                                node[f"{_SCHEMA_BASE}/url"] = [{"@value": url_value}]
                            elif author_url_fallback:
                                node[f"{_SCHEMA_BASE}/url"] = [
                                    {"@value": author_url_fallback}
                                ]
                continue
            if obj:
                node[full_prop] = [{"@value": obj}]

    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_types = {
            normalize_type(t) for t in node.get("@type", []) if isinstance(t, str)
        }
        if "Review" not in node_types:
            continue
        review_rating_prop = f"{_SCHEMA_BASE}/reviewRating"
        review_rating_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for rating_ref in node.get(review_rating_prop, []):
            if isinstance(rating_ref, dict) and rating_ref.get("@id"):
                rating_node = node_by_id.get(str(rating_ref["@id"]))
                if isinstance(rating_node, dict):
                    review_rating_pairs.append((rating_ref, rating_node))
        valid_rating_refs: list[dict[str, Any]] = []
        for rating_ref, rating_node in review_rating_pairs:
            rating_value_key = f"{_SCHEMA_BASE}/ratingValue"
            if rating_value_key not in rating_node:
                rating_value = _extract_rating_value(doc)
                if rating_value:
                    rating_node[rating_value_key] = [{"@value": rating_value}]
            if rating_value_key in rating_node:
                valid_rating_refs.append(rating_ref)
        if review_rating_pairs:
            if valid_rating_refs:
                node[review_rating_prop] = valid_rating_refs
            else:
                node.pop(review_rating_prop, None)
        if f"{_SCHEMA_BASE}/description" not in node:
            description = _xpath_first_text(
                doc, '/html/head/meta[@property="og:description"]/@content'
            ) or _xpath_first_text(doc, '/html/head/meta[@name="description"]/@content')
            if description:
                node[f"{_SCHEMA_BASE}/description"] = [{"@value": description}]
    return data


def _extract_type(node: dict[str, Any]) -> str | None:
    raw = node.get("@type")
    if isinstance(raw, list) and raw:
        raw = raw[0]
    if isinstance(raw, str):
        return normalize_type(raw)
    return None


def _extract_name(node: dict[str, Any]) -> str | None:
    for key in ("name", "headline", "title"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_text_value(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        raw = value.get("@value") or value.get("@id")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    if isinstance(value, list):
        for item in value:
            text = _extract_text_value(item)
            if text:
                return text
    return None


def _extract_name_any(node: dict[str, Any]) -> str | None:
    name = _extract_name(node)
    if name:
        return name
    for key in (
        f"{_SCHEMA_BASE}/name",
        f"{_SCHEMA_BASE}/headline",
        f"{_SCHEMA_BASE}/title",
    ):
        value = _extract_text_value(node.get(key))
        if value:
            return value
    return None


def _extract_url_any(node: dict[str, Any]) -> str | None:
    value = node.get("url")
    text = _extract_text_value(value)
    if text:
        return text
    value = node.get(f"{_SCHEMA_BASE}/url")
    text = _extract_text_value(value)
    if text:
        return text
    return None


def _local_prop_name(name: str) -> str:
    if name.startswith(_SCHEMA_BASE):
        return name.rsplit("/", 1)[-1]
    if name.startswith("schema:"):
        return name.split(":", 1)[-1]
    return name


_INDEPENDENT_PROPERTIES = {
    "author",
    "creator",
    "publisher",
    "editor",
    "contributor",
    "copyrightHolder",
    "brand",
    "manufacturer",
    "provider",
    "seller",
    "organizer",
    "performer",
    "actor",
    "director",
    "producer",
    "member",
    "memberOf",
    "affiliation",
    "parentOrganization",
    "subOrganization",
    "alumniOf",
    "sponsor",
    "about",
    "mentions",
    "mainEntity",
    "mainEntityOfPage",
    "isPartOf",
    "partOfSeries",
    "location",
    "areaServed",
}


def _is_jsonld_node(node: dict[str, Any]) -> bool:
    if "@type" in node:
        return True
    return any(isinstance(key, str) and key.startswith(_SCHEMA_BASE) for key in node)


def _ensure_node_ids(
    data: dict[str, Any] | list[Any],
    dataset_uri: str,
    url: str,
) -> None:
    seen: set[str] = set()
    replacements: dict[str, str] = {}

    def _collect(value: Any) -> None:
        if isinstance(value, dict):
            node_id = value.get("@id")
            if isinstance(node_id, str) and node_id and not node_id.startswith("_:"):
                seen.add(node_id)
            for child in value.values():
                _collect(child)
        elif isinstance(value, list):
            for item in value:
                _collect(item)

    def _assign(
        value: Any,
        counter: list[int],
        parent_id: str | None = None,
        prop_name: str | None = None,
    ) -> None:
        if isinstance(value, dict):
            if _is_jsonld_node(value):
                node_id = value.get("@id")
                local_prop = _local_prop_name(prop_name or "")
                use_parent = bool(
                    parent_id
                    and local_prop
                    and local_prop not in _INDEPENDENT_PROPERTIES
                )
                base_uri = parent_id if use_parent else dataset_uri
                needs_id = (
                    not isinstance(node_id, str)
                    or not node_id
                    or node_id.startswith("_:")
                    or (use_parent and not node_id.startswith(parent_id or ""))
                    or (not use_parent and not node_id.startswith(dataset_uri))
                )
                if needs_id:
                    type_name = _extract_type(value) or "Thing"
                    name = _extract_name_any(value)
                    if type_name == "ListItem":
                        position = _extract_text_value(
                            value.get("position")
                        ) or _extract_text_value(value.get(f"{_SCHEMA_BASE}/position"))
                        if position:
                            name = f"item-{position}"
                    if not name:
                        name = _dash_type(type_name)
                    node_url = _extract_url_any(value)
                    base_id = build_id_base(
                        base_uri, type_name, name, node_url, counter[0]
                    )
                    candidate = base_id
                    suffix = 1
                    while candidate in seen:
                        suffix += 1
                        candidate = f"{base_id}-{suffix}"
                    if isinstance(node_id, str) and node_id and node_id != candidate:
                        replacements[node_id] = candidate
                        if node_id.endswith("~iri"):
                            replacements[node_id[: -len("~iri")]] = candidate
                        else:
                            replacements[f"{node_id}~iri"] = candidate
                    value["@id"] = candidate
                    seen.add(candidate)
                    counter[0] += 1
            current_id = (
                value.get("@id") if isinstance(value.get("@id"), str) else parent_id
            )
            for key, child in value.items():
                if key in ("@id", "@type"):
                    continue
                _assign(
                    child,
                    counter,
                    current_id if isinstance(current_id, str) else None,
                    key,
                )
        elif isinstance(value, list):
            for item in value:
                _assign(item, counter, parent_id, prop_name)

    def _replace(value: Any) -> None:
        if isinstance(value, dict):
            node_id = value.get("@id")
            if isinstance(node_id, str) and node_id in replacements:
                value["@id"] = replacements[node_id]
            for child in value.values():
                _replace(child)
        elif isinstance(value, list):
            for item in value:
                _replace(item)

    _collect(data)
    _assign(data, [1])
    if replacements:
        _replace(data)


def _blank_node_errors(data: dict[str, Any] | list[Any]) -> list[str]:
    errors: list[str] = []

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            if _is_jsonld_node(value):
                node_id = value.get("@id")
                if (
                    not isinstance(node_id, str)
                    or not node_id
                    or node_id.startswith("_:")
                ):
                    errors.append(
                        "JSON-LD node missing @id or uses a blank node identifier"
                    )
            for child in value.values():
                _walk(child)
        elif isinstance(value, list):
            for item in value:
                _walk(item)

    _walk(data)
    return errors


def _review_rating_dropped(
    data: dict[str, Any] | list[Any],
    mappings: list[dict[str, Any]],
    target_type: str | None,
) -> bool:
    target = normalize_type(target_type or "Thing")
    if target != "Review":
        return False
    mapped_props = _main_mapping_props(mappings)
    if "reviewRating" not in mapped_props:
        return False
    nodes = _flatten_jsonld(data)
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_types = {
            normalize_type(t) for t in node.get("@type", []) if isinstance(t, str)
        }
        if "Review" in node_types:
            return f"{_SCHEMA_BASE}/reviewRating" not in node
    return False


def _build_id_map(
    nodes: list[dict[str, Any]],
    dataset_uri: str,
    url: str,
) -> dict[str, str]:
    id_map: dict[str, str] = {}
    for idx, node in enumerate(nodes):
        old_id = node.get("@id") or f"_:b{idx}"
        type_name = _extract_type(node) or "Thing"
        name = _extract_name_any(node) or _dash_type(type_name)
        node_url = _extract_url_any(node)
        if isinstance(old_id, str) and old_id.startswith(dataset_uri):
            new_id = old_id
        else:
            new_id = build_id(dataset_uri, type_name, name, node_url, idx + 1)
        if old_id in id_map:
            new_id = f"{new_id}-{idx}"
        id_map[str(old_id)] = new_id
    return id_map


def _rewrite_refs(
    value: Any,
    id_map: dict[str, str],
    node_map: dict[str, dict[str, Any]],
    *,
    embed_nodes: bool,
) -> Any:
    if isinstance(value, dict):
        if "@id" in value and isinstance(value["@id"], str):
            ref_id = id_map.get(value["@id"], value["@id"])
            if embed_nodes and ref_id in node_map:
                return node_map[ref_id]
            return {"@id": ref_id}
        return {
            k: _rewrite_refs(v, id_map, node_map, embed_nodes=embed_nodes)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [
            _rewrite_refs(item, id_map, node_map, embed_nodes=embed_nodes)
            for item in value
        ]
    return value


def _main_mapping_props(mappings: list[dict[str, Any]]) -> set[str]:
    schema_props = _schema_property_set()
    for mapping in mappings:
        if mapping.get("__main__"):
            props = mapping.get("props") or []
            clean: set[str] = set()
            for prop, _ in props:
                if not isinstance(prop, str):
                    continue
                name = prop[7:] if prop.startswith("schema:") else prop
                if "~" in name or "http" in name or name == "a":
                    continue
                base = name.split(".", 1)[0]
                if base in schema_props or name in schema_props:
                    clean.add(base)
            return clean
    return set()


def _missing_required_props(
    required_props: list[str],
    mapped_props: set[str],
) -> list[str]:
    missing: set[str] = set()
    mapped_base = {prop.split(".", 1)[0] for prop in mapped_props}
    for prop in required_props:
        base = prop.split(".", 1)[0]
        if base not in mapped_base:
            missing.add(prop)
    return sorted(missing)


def _missing_recommended_props(
    recommended_props: list[str],
    mapped_props: set[str],
) -> list[str]:
    missing: set[str] = set()
    mapped_base = {prop.split(".", 1)[0] for prop in mapped_props}
    for prop in recommended_props:
        base = prop.split(".", 1)[0]
        if base not in mapped_base:
            missing.add(prop)
    return sorted(missing)


def _google_allowed_properties(
    property_guides: dict[str, dict[str, list[str]]],
) -> dict[str, list[str]]:
    allowed: dict[str, list[str]] = {}
    for type_name, guide in property_guides.items():
        props = set(guide.get("required", [])) | set(guide.get("recommended", []))
        if type_name == "Review":
            props |= _REVIEW_OPTIONAL_EXTRAS
        props = sorted(props)
        allowed[type_name] = props
    return allowed


def _mapping_allowed_property_set(
    property_guides: dict[str, dict[str, list[str]]],
) -> set[str]:
    props: set[str] = set()
    for guide in property_guides.values():
        for name in guide.get("required", []) + guide.get("recommended", []):
            props.add(name.split(".", 1)[0])
    props |= _REVIEW_OPTIONAL_EXTRAS
    return props


def _mapping_violations(
    mappings: list[dict[str, Any]],
    allowed_props: set[str],
    target_type: str,
) -> list[str]:
    errors: list[str] = []
    for mapping in mappings:
        map_name = mapping.get("name", "mapping")
        map_type = normalize_type(mapping.get("type") or "")
        for prop, obj in mapping.get("props", []):
            prop_name = prop[7:] if prop.startswith("schema:") else prop
            base = prop_name.split(".", 1)[0]
            if base in {"a", "url"}:
                continue
            if "/" in base or base.startswith("http"):
                continue
            if base not in allowed_props:
                errors.append(f"{map_name}: property not allowed by Google: {base}")
            if _looks_like_xpath(obj):
                continue
            if (
                base in {"author", "reviewRating", "itemReviewed"}
                and obj.startswith("ex:")
                and obj.endswith("~iri")
            ):
                continue
            if obj.startswith("ex:") and obj.endswith("~iri"):
                continue
            errors.append(f"{map_name}: hard-coded literal for {base} is not allowed")
        if map_type == "Review":
            review_rating = [
                obj
                for prop, obj in mapping.get("props", [])
                if prop.endswith("reviewRating")
            ]
            for obj in review_rating:
                if not (obj.startswith("ex:") and obj.endswith("~iri")):
                    errors.append(f"{map_name}: reviewRating must map to a Rating node")
    return errors


def _xpath_evidence_errors(
    mappings: list[dict[str, Any]],
    xhtml: str,
) -> list[str]:
    try:
        from lxml import html as lxml_html
    except Exception:
        return []
    parser = lxml_html.HTMLParser(encoding="utf-8", recover=True)
    try:
        doc = lxml_html.document_fromstring(xhtml, parser=parser)
    except Exception:
        return []
    errors: list[str] = []
    for mapping in mappings:
        map_name = mapping.get("name", "mapping")
        for prop, obj in mapping.get("props", []):
            prop_name = prop[7:] if prop.startswith("schema:") else prop
            if prop_name == "url":
                continue
            if not _looks_like_xpath(obj):
                continue
            try:
                result = doc.xpath(_simplify_xpath(obj))
            except Exception:
                errors.append(f"{map_name}: invalid XPath for {prop_name}")
                continue
            if not result:
                errors.append(f"{map_name}: XPath returned no results for {prop_name}")
                continue
            if isinstance(result, list) and all(
                (isinstance(item, str) and not item.strip()) for item in result
            ):
                errors.append(f"{map_name}: XPath returned empty text for {prop_name}")
    return errors


def _xpath_reusability_warnings(mappings: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    id_with_digits = re.compile(r"@id\\s*=\\s*['\"][^'\"]*\\d[^'\"]*['\"]")
    for mapping in mappings:
        map_name = mapping.get("name", "mapping")
        for prop, obj in mapping.get("props", []):
            prop_name = prop[7:] if prop.startswith("schema:") else prop
            if not _looks_like_xpath(obj):
                continue
            candidate = obj.replace('\\"', '"').replace("\\'", "'")
            if id_with_digits.search(candidate):
                warnings.append(
                    f"{map_name}: XPath for {prop_name} uses a numeric @id; prefer a reusable selector."
                )
    return warnings


def _mapping_type_sanity(
    mappings: list[dict[str, Any]],
    expected_types: dict[str, tuple[str, ...]],
) -> list[str]:
    errors: list[str] = []
    mapping_types = {
        m.get("name"): normalize_type(m.get("type") or "") for m in mappings
    }
    for mapping in mappings:
        map_name = mapping.get("name")
        for prop, obj in mapping.get("props", []):
            prop_name = prop[7:] if prop.startswith("schema:") else prop
            if obj.startswith("ex:") and obj.endswith("~iri"):
                target = obj.split("ex:", 1)[1].split("~", 1)[0]
                expected = expected_types.get(prop_name)
                if expected:
                    actual = mapping_types.get(target, "")
                    if actual and actual not in expected:
                        errors.append(
                            f"{map_name}: {prop_name} must map to {expected}, got {actual}"
                        )
    return errors


def _format_result_path(value: Identifier | None) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, URIRef):
        return _short_schema_name(value) or str(value)
    return str(value)


def _validation_messages(
    result: ValidationResult, max_items: int = 20
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    count = 0
    for res in result.report_graph.subjects(RDF.type, _SH.ValidationResult):
        severity = result.report_graph.value(res, _SH.resultSeverity)
        message = result.report_graph.value(res, _SH.resultMessage)
        path = result.report_graph.value(res, _SH.resultPath)
        source_shape = result.report_graph.value(res, _SH.sourceShape)
        source_label = result.shape_source_map.get(source_shape, "unknown")
        line = f"{_format_result_path(path)}: {message or 'validation error'} (shape: {source_label})"
        if severity == _SH.Warning:
            warnings.append(line)
        else:
            errors.append(line)
        count += 1
        if count >= max_items:
            break
    return errors, warnings


def _validation_messages_for_types(
    result: ValidationResult,
    allowed_types: set[str],
    max_items: int = 20,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    count = 0
    for res in result.report_graph.subjects(RDF.type, _SH.ValidationResult):
        severity = result.report_graph.value(res, _SH.resultSeverity)
        message = result.report_graph.value(res, _SH.resultMessage)
        path = result.report_graph.value(res, _SH.resultPath)
        source_shape = result.report_graph.value(res, _SH.sourceShape)
        source_label = result.shape_source_map.get(source_shape, "unknown")
        focus = result.report_graph.value(res, _SH.focusNode)
        focus_types: set[str] = set()
        if focus is not None:
            for t in result.data_graph.objects(focus, RDF.type):
                if isinstance(t, URIRef):
                    focus_types.add(normalize_type(str(t)))
        relevant = not focus_types or bool(focus_types & allowed_types)
        line = f"{_format_result_path(path)}: {message or 'validation error'} (shape: {source_label})"
        if severity == _SH.Warning or not relevant:
            warnings.append(line)
        else:
            errors.append(line)
        count += 1
        if count >= max_items:
            break
    return errors, warnings


def normalize_jsonld(
    data: dict[str, Any] | list[Any],
    dataset_uri: str,
    url: str,
    target_type: str | None,
    *,
    embed_nodes: bool = True,
) -> dict[str, Any]:
    data = _normalize_iri_suffixes(data)
    nodes = _collect_jsonld_nodes(data)
    if not nodes:
        raise RuntimeError("No JSON-LD nodes produced by morph-kgc.")

    target = normalize_type(target_type) if target_type else None
    main_node: dict[str, Any] | None = None
    main_old_id = "_:b0"
    for idx, node in enumerate(nodes):
        node_type = _extract_type(node)
        if target and node_type == target:
            main_node = node
            main_old_id = str(node.get("@id") or f"_:b{idx}")
            break
    if main_node is None:
        main_node = nodes[0]
        main_old_id = str(main_node.get("@id") or "_:b0")

    id_map = _build_id_map(nodes, dataset_uri, url)
    node_map: dict[str, dict[str, Any]] = {}
    for idx, node in enumerate(nodes):
        old_id = str(node.get("@id") or f"_:b{idx}")
        new_id = id_map[old_id]
        node["@id"] = new_id
        node_map[new_id] = node

    for node in nodes:
        for key, value in list(node.items()):
            if key in ("@id", "@type"):
                continue
            node[key] = _rewrite_refs(value, id_map, node_map, embed_nodes=embed_nodes)

    main_id = id_map.get(main_old_id)
    if not main_id:
        raise RuntimeError("Failed to resolve main node @id.")
    if embed_nodes:
        main = node_map[main_id]
        main["@context"] = _SCHEMA_BASE
        blank_nodes = _blank_node_errors(main)
        if blank_nodes:
            raise RuntimeError("Blank nodes are not allowed in JSON-LD output.")
        return main
    for node in node_map.values():
        node.setdefault("@context", _SCHEMA_BASE)
    graph = {"@context": _SCHEMA_BASE, "@graph": list(node_map.values())}
    blank_nodes = _blank_node_errors(graph)
    if blank_nodes:
        raise RuntimeError("Blank nodes are not allowed in JSON-LD output.")
    return graph


def generate_from_agent(
    url: str,
    html: str,
    xhtml: str,
    cleaned_xhtml: str,
    api_key: str,
    dataset_uri: str,
    target_type: str | None,
    workdir: Path,
    debug: bool = False,
    max_retries: int = 2,
    max_nesting_depth: int = 2,
    quality_check: bool = True,
    log: Callable[[str], None] | None = None,
) -> tuple[str, dict[str, Any]]:
    debug_path = workdir / "agent_debug.json" if debug else None
    target_name = normalize_type(target_type or "Thing")
    property_guides = property_guides_with_related(target_name, max_nesting_depth)
    allowed_properties = _google_allowed_properties(property_guides)
    allowed_property_set = _mapping_allowed_property_set(property_guides)
    workdir.mkdir(parents=True, exist_ok=True)
    requirements_path = workdir / "requirements.json"
    requirements_path.write_text(
        json.dumps(
            {
                "target_type": target_name,
                "max_depth": max_nesting_depth,
                "types": property_guides,
                "allowed_properties": allowed_properties,
            },
            indent=2,
        )
    )
    html_path = (workdir / "rendered.html").resolve()
    html_path.write_text(html)
    xhtml_path = (workdir / "page.xhtml").resolve()
    xhtml_path.write_text(xhtml)
    cleaned_path = (workdir / "page.cleaned.xhtml").resolve()
    cleaned_path.write_text(cleaned_xhtml)

    shape_specs = shape_specs_for_types(list(property_guides.keys()))
    mapping_validation_path = workdir / "mapping.validation.json"
    mapping_jsonld_path = workdir / "mapping.jsonld"

    yarrml = ""
    mappings: list[dict[str, Any]] = []
    missing_required: list[str] = []
    previous_yarrml: str | None = None
    validation_errors: list[str] | None = None
    validation_report: list[str] | None = None
    missing_recommended: list[str] = []
    xpath_warnings: list[str] = []
    quality_feedback: list[str] | None = None
    quality_score: int | None = None
    jsonld_raw: dict[str, Any] | list[Any] | None = None
    normalized_jsonld: dict[str, Any] | None = None

    for attempt in range(max_retries + 1):
        yarrml = ask_agent_for_yarrml(
            api_key,
            url,
            cleaned_xhtml,
            target_type,
            debug=debug,
            debug_path=debug_path,
            property_guides=property_guides,
            missing_required=missing_required if attempt > 0 else None,
            missing_recommended=missing_recommended if attempt > 0 else None,
            previous_yarrml=previous_yarrml if attempt > 0 else None,
            validation_errors=validation_errors if attempt > 0 else None,
            validation_report=validation_report if attempt > 0 else None,
            xpath_warnings=xpath_warnings if attempt > 0 else None,
            allow_properties=allowed_properties,
            quality_feedback=quality_feedback if attempt > 0 else None,
        )

        yarrml, mappings = _normalize_agent_yarrml(
            yarrml,
            url,
            cleaned_path.as_posix(),
            target_type,
        )
        yarrml_path = workdir / "mapping.yarrml"
        rml_path = workdir / "mapping.ttl"
        yarrml_path.write_text(yarrml)

        try:
            _run_yarrrml_parser(yarrml_path, rml_path)
            _ensure_subject_termtype_iri(rml_path)
            _normalize_reference_formulation(rml_path)
            jsonld_raw = _materialize_jsonld(rml_path)
            jsonld_raw = _fill_jsonld_from_mappings(jsonld_raw, mappings, cleaned_xhtml)
            _ensure_node_ids(jsonld_raw, dataset_uri, url)
            mapping_jsonld_path.write_text(json.dumps(jsonld_raw, indent=2))
            normalized_jsonld = postprocess_jsonld(
                jsonld_raw,
                mappings,
                cleaned_xhtml,
                dataset_uri,
                url,
                target_type=target_type,
            )
            final_jsonld_path = workdir / "structured-data.jsonld"
            final_jsonld_path.write_text(json.dumps(normalized_jsonld, indent=2))
            validation_result = validate_file(
                str(final_jsonld_path), shape_specs=shape_specs
            )
            errors, warnings = _validation_messages_for_types(
                validation_result,
                set(property_guides.keys()),
            )
            validation_errors = errors or None
            validation_report = (
                validation_result.report_text.splitlines()
                if validation_result
                else None
            )
        except Exception as exc:
            mapping_validation_path.write_text(
                json.dumps(
                    {
                        "conforms": False,
                        "warning_count": 0,
                        "errors": [str(exc)],
                        "warnings": [],
                    },
                    indent=2,
                )
            )
            validation_errors = [str(exc)]
            validation_report = None
            previous_yarrml = yarrml
            continue

        mapped_props = _main_mapping_props(mappings)
        required_props = property_guides.get(target_name, {}).get("required", [])
        recommended_props = property_guides.get(target_name, {}).get("recommended", [])
        missing_required = _missing_required_props(required_props, mapped_props)
        missing_recommended = _missing_recommended_props(
            recommended_props, mapped_props
        )
        mapping_errors: list[str] = []
        mapping_errors.extend(
            _mapping_violations(mappings, allowed_property_set, target_name)
        )
        evidence_warnings = _xpath_evidence_errors(mappings, cleaned_xhtml)
        reusability_warnings = _xpath_reusability_warnings(mappings)
        expected_types = {
            "reviewRating": ("Rating",),
            "author": ("Person", "Organization"),
        }
        mapping_errors.extend(_mapping_type_sanity(mappings, expected_types))
        if reusability_warnings:
            mapping_errors.extend(reusability_warnings)
        warnings_out: list[str] = list(warnings) if "warnings" in locals() else []
        if evidence_warnings:
            warnings_out.extend(evidence_warnings)
        if reusability_warnings:
            warnings_out.extend(reusability_warnings)
        if missing_required:
            warnings_out.append(
                f"Missing required properties: {', '.join(missing_required)}"
            )
        if mapping_errors:
            mapping_validation_path.write_text(
                json.dumps(
                    {
                        "conforms": False,
                        "warning_count": validation_result.warning_count
                        if "validation_result" in locals()
                        else 0,
                        "errors": mapping_errors,
                        "warnings": warnings_out,
                        "shacl_errors": errors if "errors" in locals() else [],
                    },
                    indent=2,
                )
            )
            validation_errors = mapping_errors
            validation_report = None
            xpath_warnings = warnings_out
        else:
            if _review_rating_dropped(jsonld_raw, mappings, target_type):
                warnings_out.append("Review ratingValue missing; reviewRating dropped.")
            mapping_validation_path.write_text(
                json.dumps(
                    {
                        "conforms": validation_result.conforms
                        if "validation_result" in locals()
                        else True,
                        "warning_count": validation_result.warning_count
                        if "validation_result" in locals()
                        else 0,
                        "errors": errors if "errors" in locals() else [],
                        "warnings": warnings_out,
                    },
                    indent=2,
                )
            )
            validation_errors = errors or None
            validation_report = (
                validation_result.report_text.splitlines()
                if validation_result
                else None
            )
            xpath_warnings = warnings_out
            if quality_check:
                quality_score = None
                quality_feedback = None
                try:
                    quality_payload = ask_agent_for_quality(
                        api_key,
                        url,
                        cleaned_xhtml,
                        normalized_jsonld,
                        property_guides,
                        target_type,
                    )
                except RuntimeError:
                    quality_payload = None
                if isinstance(quality_payload, dict):
                    score = quality_payload.get("score")
                    if isinstance(score, (int, float)):
                        quality_score = int(score)
                    missing = quality_payload.get("missing_in_jsonld")
                    notes = quality_payload.get("notes")
                    suggested = quality_payload.get("suggested_xpath")
                    feedback: list[str] = []
                    if isinstance(missing, list) and missing:
                        feedback.append("Missing in JSON-LD (present in XHTML):")
                        feedback.extend([str(item) for item in missing])
                    if isinstance(suggested, dict) and suggested:
                        feedback.append("Suggested XPath for missing properties:")
                        for key, value in suggested.items():
                            feedback.append(f"- {key}: {value}")
                    if isinstance(notes, list) and notes:
                        feedback.append("Notes:")
                        feedback.extend([str(item) for item in notes])
                    if feedback:
                        feedback.append(
                            f"Quality score: {quality_score}"
                            if quality_score is not None
                            else "Quality score unavailable"
                        )
                        quality_feedback = feedback
        if validation_errors is None and (
            not missing_required or attempt >= max_retries
        ):
            if (
                not quality_check
                or quality_score is None
                or quality_score >= 7
                or attempt >= max_retries
            ):
                break
        previous_yarrml = yarrml

    if jsonld_raw is None:
        raise RuntimeError(
            "Failed to produce JSON-LD from the generated YARRRML mapping."
        )
    if validation_errors:
        logger = logging.getLogger("worai")
        logger.warning(
            "YARRRML mapping failed validation after retries; proceeding anyway. "
            f"See {mapping_validation_path} for details."
        )

    if normalized_jsonld is None:
        normalized_jsonld = normalize_jsonld(
            jsonld_raw, dataset_uri, url, target_type, embed_nodes=False
        )
    jsonld = normalized_jsonld
    return yarrml, jsonld


__all__ = [
    "StructuredDataOptions",
    "StructuredDataResult",
    "build_output_basename",
    "ensure_no_blank_nodes",
    "generate_from_agent",
    "get_dataset_uri",
    "get_dataset_uri_async",
    "make_reusable_yarrrml",
    "materialize_yarrrml_jsonld",
    "normalize_type",
    "normalize_yarrrml_mappings",
    "postprocess_jsonld",
    "shape_specs_for_type",
]
