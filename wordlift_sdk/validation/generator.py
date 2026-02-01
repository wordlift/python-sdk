"""SHACL generator utilities."""

from __future__ import annotations

import argparse
import html as html_lib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import requests
from rdflib import Graph, Namespace, RDF, RDFS, URIRef
from tqdm import tqdm

SEARCH_GALLERY_URL = "https://developers.google.com/search/docs/appearance/structured-data/search-gallery"
FEATURE_URL_RE = re.compile(
    r'href="(/search/docs/appearance/structured-data/[^"#?]+)"', re.IGNORECASE
)
TOKEN_RE = re.compile(
    r"(<table[^>]*>.*?</table>|<p[^>]*>.*?</p>|<h2[^>]*>.*?</h2>|<h3[^>]*>.*?</h3>)",
    re.DOTALL | re.IGNORECASE,
)
ROW_RE = re.compile(r"<tr[^>]*>.*?</tr>", re.DOTALL | re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")

SCHEMA_JSONLD_URL = "https://schema.org/version/latest/schemaorg-current-https.jsonld"

SCHEMA_VOCAB = Namespace("https://schema.org/")
SCHEMA_DATA = Namespace("http://schema.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")
RDF_NS = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")


@dataclass
class FeatureData:
    url: str
    types: dict[str, dict[str, set[str]]]


@dataclass
class PropertyRange:
    prop: URIRef
    ranges: list[URIRef]


def _strip_tags(text: str) -> str:
    return html_lib.unescape(TAG_RE.sub("", text)).strip()


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _extract_schema_types(fragment: str) -> list[str]:
    types = []
    for match in re.findall(r"https?://schema\.org/([A-Za-z0-9]+)", fragment):
        types.append(match)

    if types:
        return _unique(types)

    if fragment.lower().startswith("<h"):
        code_match = re.findall(
            r"<code[^>]*>(.*?)</code>", fragment, re.DOTALL | re.IGNORECASE
        )
        for item in code_match:
            value = _strip_tags(item)
            for token in re.findall(r"[A-Z][A-Za-z0-9]*", value):
                types.append(token)
        return _unique(types)

    return []


def _table_kind(table_html: str) -> str | None:
    header_match = re.search(r"<th[^>]*>\s*([^<]+)\s*</th>", table_html, re.IGNORECASE)
    if not header_match:
        return None
    header = _strip_tags(header_match.group(1)).lower()
    if "required properties" in header:
        return "required"
    if "recommended properties" in header:
        return "recommended"
    return None


def _extract_properties(table_html: str) -> list[str]:
    props: list[str] = []
    for row in ROW_RE.findall(table_html):
        td_match = re.search(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        if not td_match:
            continue
        td_html = td_match.group(1)
        code_match = re.search(
            r"<code[^>]*>(.*?)</code>", td_html, re.DOTALL | re.IGNORECASE
        )
        if not code_match:
            continue
        raw = _strip_tags(code_match.group(1))
        for token in re.findall(
            r"[A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z][A-Za-z0-9]*)*", raw
        ):
            if token.startswith("@"):
                continue
            if token[0].isupper() and "." not in token:
                continue
            props.append(token)
    return _unique(props)


def _feature_urls_from_gallery(html: str) -> list[str]:
    urls: list[str] = []
    for match in FEATURE_URL_RE.findall(html):
        url = f"https://developers.google.com{match}".rstrip("/")
        if url.endswith("/search-gallery"):
            continue
        if url.endswith("/structured-data"):
            continue
        if url not in urls:
            urls.append(url)
    return urls


def _parse_feature(html: str, url: str) -> FeatureData:
    current_types: list[str] = []
    type_data: dict[str, dict[str, set[str]]] = {}

    for token in TOKEN_RE.findall(html):
        if token.lower().startswith(("<p", "<h2", "<h3")):
            types = _extract_schema_types(token)
            if types:
                current_types = types
            continue

        if token.lower().startswith("<table"):
            kind = _table_kind(token)
            if not kind:
                continue
            props = _extract_properties(token)
            if not props:
                continue
            target_types = current_types or ["Thing"]
            for t in target_types:
                bucket = type_data.setdefault(
                    t, {"required": set(), "recommended": set()}
                )
                bucket[kind].update(props)

    for t, bucket in type_data.items():
        bucket["recommended"].difference_update(bucket["required"])

    return FeatureData(url=url, types=type_data)


def _prop_path(prop: str) -> str:
    parts = prop.split(".")
    if len(parts) == 1:
        return f"schema:{parts[0]}"
    seq = " ".join(f"schema:{part}" for part in parts)
    return f"( {seq} )"


def _write_feature(feature: FeatureData, output_path: Path, overwrite: bool) -> bool:
    if output_path.exists() and not overwrite:
        return False

    lines: list[str] = []
    slug = output_path.stem
    prefix_base = f"https://wordlift.io/shacl/google/{slug}/"
    lines.append(f"@prefix : <{prefix_base}> .")
    lines.append("@prefix sh: <http://www.w3.org/ns/shacl#> .")
    lines.append("@prefix schema: <http://schema.org/> .")
    lines.append("")
    lines.append(f"# Source: {feature.url}")
    lines.append(f"# Generated: {datetime.utcnow().isoformat(timespec='seconds')}Z")
    lines.append(
        "# Notes: required properties => errors; recommended properties => warnings."
    )
    lines.append("")

    for type_name in sorted(feature.types.keys()):
        bucket = feature.types[type_name]
        shape_name = f":google_{type_name}Shape"
        lines.append(shape_name)
        lines.append("  a sh:NodeShape ;")
        lines.append(f"  sh:targetClass schema:{type_name} ;")

        for prop in sorted(bucket["required"]):
            path = _prop_path(prop)
            lines.append("  sh:property [")
            lines.append(f"    sh:path {path} ;")
            lines.append("    sh:minCount 1 ;")
            lines.append("  ] ;")

        for prop in sorted(bucket["recommended"]):
            path = _prop_path(prop)
            lines.append("  sh:property [")
            lines.append(f"    sh:path {path} ;")
            lines.append("    sh:minCount 1 ;")
            lines.append("    sh:severity sh:Warning ;")
            lines.append(f'    sh:message "Recommended by Google: {prop}." ;')
            lines.append("  ] ;")

        lines.append(".")
        lines.append("")

    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return True


def generate_google_shacls(
    output_dir: Path, overwrite: bool, limit: int, only: list[str] | None
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)

    gallery_html = requests.get(SEARCH_GALLERY_URL, timeout=30).text
    feature_urls = _feature_urls_from_gallery(gallery_html)

    if only:
        wanted = {slug.strip().rstrip("/") for slug in only}
        feature_urls = [url for url in feature_urls if url.rsplit("/", 1)[-1] in wanted]

    if limit:
        feature_urls = feature_urls[:limit]

    generated = 0
    skipped = 0

    for url in tqdm(feature_urls, desc="Generating SHACLs", unit="feature"):
        slug = url.rsplit("/", 1)[-1]
        output_name = f"google-{slug}.ttl"
        output_path = output_dir / output_name

        if slug == "review-snippet" and output_path.exists() is False:
            curated = output_dir / "review-snippet.ttl"
            if curated.exists() and not overwrite:
                skipped += 1
                continue

        html = requests.get(url, timeout=30).text
        feature = _parse_feature(html, url)
        if not feature.types:
            skipped += 1
            continue

        if _write_feature(feature, output_path, overwrite):
            generated += 1
        else:
            skipped += 1

    print(f"Generated: {generated}")
    print(f"Skipped: {skipped}")
    print(f"Total: {len(feature_urls)}")
    return 0


def _datatype_shapes(datatype: str) -> list[dict[str, str]]:
    if datatype == "Text":
        return [
            {"datatype": str(XSD.string)},
            {"datatype": str(RDF_NS.langString)},
        ]
    if datatype == "URL":
        return [{"datatype": str(XSD.anyURI)}]
    if datatype == "Boolean":
        return [{"datatype": str(XSD.boolean)}]
    if datatype == "Date":
        return [{"datatype": str(XSD.date)}]
    if datatype == "DateTime":
        return [{"datatype": str(XSD.dateTime)}]
    if datatype == "Time":
        return [{"datatype": str(XSD.time)}]
    if datatype == "Integer":
        return [{"datatype": str(XSD.integer)}]
    if datatype == "Float":
        return [{"datatype": str(XSD.float)}]
    if datatype == "Number":
        return [
            {"datatype": str(XSD.integer)},
            {"datatype": str(XSD.decimal)},
            {"datatype": str(XSD.double)},
        ]
    return []


def _short_name(uri: URIRef) -> str:
    value = str(uri)
    if value.startswith(str(SCHEMA_VOCAB)):
        return value[len(str(SCHEMA_VOCAB)) :]
    if value.startswith(str(SCHEMA_DATA)):
        return value[len(str(SCHEMA_DATA)) :]
    return value.rsplit("/", 1)[-1]


def _collect_classes(graph: Graph) -> list[URIRef]:
    classes = set(graph.subjects(RDF.type, RDFS.Class))
    classes.update(graph.subjects(RDF.type, SCHEMA_VOCAB.Class))
    return sorted(classes, key=str)


def _collect_properties(graph: Graph) -> list[URIRef]:
    props = set(graph.subjects(RDF.type, RDF.Property))
    return sorted(props, key=str)


def _collect_domain_ranges(
    graph: Graph, prop: URIRef
) -> list[tuple[URIRef, list[URIRef]]]:
    domains = list(graph.objects(prop, SCHEMA_VOCAB.domainIncludes))
    ranges = list(graph.objects(prop, SCHEMA_VOCAB.rangeIncludes))
    if not domains:
        return []
    return [(domain, ranges) for domain in domains]


def _render_property_shape(prop: URIRef, ranges: list[URIRef]) -> list[str]:
    lines: list[str] = []
    lines.append("  sh:property [")
    lines.append(f"    sh:path schema:{_short_name(prop)} ;")
    lines.append("    sh:severity sh:Warning ;")

    range_constraints: list[str] = []
    for r in ranges:
        name = _short_name(r)
        datatype_shapes = _datatype_shapes(name)
        if datatype_shapes:
            for shape in datatype_shapes:
                range_constraints.append(f"[ sh:datatype <{shape['datatype']}> ]")
        else:
            range_constraints.append(f"[ sh:class schema:{name} ]")

    if range_constraints:
        if len(range_constraints) == 1:
            lines.append(f"    sh:or ( {range_constraints[0]} ) ;")
        else:
            lines.append("    sh:or (")
            for rc in range_constraints:
                lines.append(f"      {rc}")
            lines.append("    ) ;")

    lines.append(f'    sh:message "Schema.org range check: {_short_name(prop)}." ;')
    lines.append("  ] ;")
    return lines


def generate_schema_shacls(output_file: Path, overwrite: bool) -> int:
    output_path = output_file
    if output_path.exists() and not overwrite:
        print(f"Output exists: {output_path}")
        return 1

    response = requests.get(SCHEMA_JSONLD_URL, timeout=60)
    response.raise_for_status()

    graph = Graph()
    graph.parse(data=response.text, format="json-ld")

    classes = _collect_classes(graph)
    props = _collect_properties(graph)

    class_props: dict[URIRef, list[PropertyRange]] = {cls: [] for cls in classes}

    for prop in tqdm(props, desc="Collecting properties", unit="prop"):
        for domain, ranges in _collect_domain_ranges(graph, prop):
            if domain not in class_props:
                class_props[domain] = []
            class_props[domain].append(PropertyRange(prop=prop, ranges=ranges))

    lines: list[str] = []
    lines.append("@prefix : <https://wordlift.io/shacl/schemaorg-grammar/> .")
    lines.append(f"@prefix sh: <{SH}> .")
    lines.append(f"@prefix schema: <{SCHEMA_DATA}> .")
    lines.append("")
    lines.append(f"# Source: {SCHEMA_JSONLD_URL}")
    lines.append(f"# Generated: {datetime.utcnow().isoformat(timespec='seconds')}Z")
    lines.append(
        "# Notes: schema.org grammar checks only; all constraints are warnings."
    )
    lines.append("")

    for cls in tqdm(classes, desc="Writing shapes", unit="class"):
        props_for_class = class_props.get(cls, [])
        if not props_for_class:
            continue
        shape_name = f":schema_{_short_name(cls)}Shape"
        lines.append(shape_name)
        lines.append("  a sh:NodeShape ;")
        lines.append(f"  sh:targetClass schema:{_short_name(cls)} ;")

        for prop_range in props_for_class:
            lines.extend(_render_property_shape(prop_range.prop, prop_range.ranges))

        lines.append(".")
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


def google_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate Google Search Gallery SHACL shapes."
    )
    parser.add_argument(
        "--output-dir",
        default="worai/validation/shacls",
        help="Directory for generated SHACL files.",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing files."
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="Limit number of features (0 = all)."
    )
    parser.add_argument(
        "--only", nargs="*", help="Only generate for specified feature slugs."
    )
    args = parser.parse_args(argv)
    return generate_google_shacls(
        Path(args.output_dir), args.overwrite, args.limit, args.only
    )


def schema_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Schema.org grammar SHACLs.")
    parser.add_argument(
        "--output-file",
        default="worai/validation/shacls/schemaorg-grammar.ttl",
        help="Output SHACL file.",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing file."
    )
    args = parser.parse_args(argv)
    return generate_schema_shacls(Path(args.output_file), args.overwrite)
