"""SHACL generator utilities."""

from __future__ import annotations

import argparse
import html as html_lib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests
from rdflib import Graph, Namespace, RDF, RDFS, URIRef
from rdflib.collection import Collection
from tqdm import tqdm

SEARCH_GALLERY_URL = "https://developers.google.com/search/docs/appearance/structured-data/search-gallery"
FEATURE_URL_RE = re.compile(
    r'href="(/search/docs/appearance/structured-data/[^"#?]+)"', re.IGNORECASE
)
TOKEN_RE = re.compile(
    r"(<table[^>]*>.*?</table>|<p[^>]*>.*?</p>|<h2[^>]*>.*?</h2>|<h3[^>]*>.*?</h3>|<h4[^>]*>.*?</h4>|<ul[^>]*>.*?</ul>|<ol[^>]*>.*?</ol>)",
    re.DOTALL | re.IGNORECASE,
)
ROW_RE = re.compile(r"<tr[^>]*>.*?</tr>", re.DOTALL | re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
LIST_ITEM_RE = re.compile(r"<li[^>]*>.*?</li>", re.DOTALL | re.IGNORECASE)
ONE_OF_RE = re.compile(
    r"(one of the following properties|one of the following|require either|must include one of|must provide one of|at least two statements)",
    re.IGNORECASE,
)
ONE_OF_VALUE_RE = re.compile(
    r"(one of the following\s+values?|one of the following\s+types?|following\s+values?|following\s+types?)",
    re.IGNORECASE,
)
FALLBACK_RE = re.compile(r"\bif you do(?:n['’]?t| not)\s+include\b", re.IGNORECASE)
TYPE_LIST_RE = re.compile(
    r"must be based on one of the following\s+schema\.org types",
    re.IGNORECASE,
)
CONDITIONAL_REQUIRED_RE = re.compile(
    r"(required when|only required if|required if)\b",
    re.IGNORECASE,
)

SCHEMA_JSONLD_URL = "https://schema.org/version/latest/schemaorg-current-https.jsonld"

SCHEMA_VOCAB = Namespace("https://schema.org/")
SCHEMA_DATA = Namespace("http://schema.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")
RDF_NS = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")

GS1_VOC_URL = "https://ref.gs1.org/voc/data/gs1Voc.ttl"
GS1_NS = Namespace("https://ref.gs1.org/voc/")
OWL_NS = Namespace("http://www.w3.org/2002/07/owl#")


@dataclass
class FeatureData:
    url: str
    types: dict[str, dict[str, set[str]]]
    one_of: dict[str, list[set[str]]] = field(default_factory=dict)
    one_of_option_groups: dict[str, list[list[set[str]]]] = field(default_factory=dict)
    one_of_recommended: dict[str, list[set[str]]] = field(default_factory=dict)
    one_of_option_groups_recommended: dict[str, list[list[set[str]]]] = field(
        default_factory=dict
    )


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
        if types:
            return _unique(types)

        # Fallback for plain headings such as "Quiz" or "DataFeed entity".
        heading_text = _strip_tags(fragment)
        heading_text = re.sub(r"\s+", " ", heading_text).strip()
        head_match = re.match(r"^([A-Z][A-Za-z0-9]+)(.*)$", heading_text)
        if head_match:
            head_token = head_match.group(1)
            tail = head_match.group(2).strip().lower()
            ignored_heads = {
                "Feature",
                "Prepare",
                "Add",
                "How",
                "Examples",
                "Example",
                "Google",
                "JSON",
                "LD",
                "IPTC",
                "Structured",
                "Data",
                "Required",
                "Recommended",
            }
            allowed_tails = {
                "",
                "entity",
                "entities",
                "object",
                "objects",
                "member",
                "(member)",
            }
            if tail in allowed_tails and head_token not in ignored_heads:
                return [head_token]
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


def _extract_property_tokens(raw: str) -> list[str]:
    value = _strip_tags(raw)
    if "://" in value or "schema.org/" in value or "/" in value:
        return []

    tokens: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z][A-Za-z0-9]*)*", value):
        if token.startswith("@"):
            continue
        if "." in token:
            head, tail = token.split(".", 1)
            if head and head[0].isupper():
                token = tail
        if token.lower() in JSONLD_META_TOKEN_BLACKLIST:
            continue
        if token[0].isupper() and "." not in token:
            continue
        tokens.append(token)
    return _unique(tokens)


def _extract_code_tokens(fragment: str) -> list[str]:
    tokens: list[str] = []
    for match in re.findall(
        r"<code[^>]*>(.*?)</code>", fragment, re.DOTALL | re.IGNORECASE
    ):
        tokens.extend(_extract_property_tokens(match))
    return _unique(tokens)


def _expand_option_branches(
    base_props: set[str], one_of_groups: list[set[str]]
) -> list[set[str]]:
    branches: list[set[str]] = [set(base_props)]
    for group in one_of_groups:
        if not group:
            continue
        expanded: list[set[str]] = []
        for branch in branches:
            for prop in sorted(group):
                expanded.append(set(branch) | {prop})
        branches = expanded
    return branches


def _extract_table_properties(
    table_html: str,
) -> tuple[list[str], list[set[str]], list[list[set[str]]]]:
    props: list[str] = []
    one_of_groups: list[set[str]] = []
    option_groups: list[list[set[str]]] = []
    option_order: list[str] = []
    option_props: dict[str, set[str]] = {}
    option_one_of_groups: dict[str, list[set[str]]] = {}

    option_label_re = re.compile(r"^\s*option\s+([a-z0-9]+)\s*$", re.IGNORECASE)
    current_option: str | None = None

    for row in ROW_RE.findall(table_html):
        row_text = _strip_tags(row).lower()
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        if not tds:
            continue
        if len(tds) == 1:
            option_label = _strip_tags(tds[0])
            option_match = option_label_re.match(option_label)
            if option_match:
                current_option = option_match.group(1).upper()
                if current_option not in option_props:
                    option_order.append(current_option)
                    option_props[current_option] = set()
                    option_one_of_groups[current_option] = []
                continue

        primary_tokens = _extract_code_tokens(tds[0])
        row_has_schema_ref = "schema.org/" in row.lower()
        if (
            len(primary_tokens) == 1
            and "." not in primary_tokens[0]
            and not row_has_schema_ref
            and len(tds) > 1
        ):
            value_text = _strip_tags(tds[1]).lower()
            if any(
                marker in value_text
                for marker in (
                    "whether the",
                    "use one of the following",
                    "select one of the following",
                    "the type of",
                )
            ):
                primary_tokens = []
        row_tokens = _extract_code_tokens(row)

        if ONE_OF_RE.search(row_text) and not ONE_OF_VALUE_RE.search(row_text):
            list_props: list[str] = []
            for td in tds:
                for list_html in re.findall(
                    r"<ul[^>]*>.*?</ul>|<ol[^>]*>.*?</ol>",
                    td,
                    re.DOTALL | re.IGNORECASE,
                ):
                    list_props.extend(_extract_list_properties(list_html))
            candidate_props = _unique(list_props)
            if len(candidate_props) >= 2:
                group = set(candidate_props)
                if current_option:
                    option_one_of_groups[current_option].append(group)
                else:
                    one_of_groups.append(group)
            elif not candidate_props and len(primary_tokens) >= 2:
                group = set(primary_tokens)
                if current_option:
                    option_one_of_groups[current_option].append(group)
                else:
                    one_of_groups.append(group)
            else:
                if current_option:
                    option_props[current_option].update(primary_tokens)
                else:
                    props.extend(primary_tokens)
        elif len(primary_tokens) > 1 and " or " in row_text:
            if current_option:
                option_one_of_groups[current_option].append(set(primary_tokens))
            else:
                one_of_groups.append(set(primary_tokens))
        elif primary_tokens and FALLBACK_RE.search(row_text):
            # Treat explicit fallback prose as an alternative requirement
            # (for example: "Google supports url if you don't include contentUrl").
            fallback_tokens = [
                token for token in row_tokens if token not in primary_tokens
            ]
            fallback_group = set(primary_tokens) | set(fallback_tokens)
            if len(fallback_group) >= 2:
                if current_option:
                    option_one_of_groups[current_option].append(fallback_group)
                else:
                    one_of_groups.append(fallback_group)
            else:
                if current_option:
                    option_props[current_option].update(primary_tokens)
                else:
                    props.extend(primary_tokens)
        else:
            if current_option:
                option_props[current_option].update(primary_tokens)
            else:
                props.extend(primary_tokens)

    if len(option_order) >= 2:
        branches: list[set[str]] = []
        for option_name in option_order:
            branches.extend(
                _expand_option_branches(
                    option_props[option_name], option_one_of_groups[option_name]
                )
            )
        if branches:
            option_groups.append(branches)
    elif len(option_order) == 1:
        option_name = option_order[0]
        props.extend(option_props[option_name])
        one_of_groups.extend(option_one_of_groups[option_name])

    return _unique(props), one_of_groups, option_groups


def _extract_list_properties(list_html: str) -> list[str]:
    props: list[str] = []
    for item in LIST_ITEM_RE.findall(list_html):
        code_matches = re.findall(
            r"<code[^>]*>(.*?)</code>", item, re.DOTALL | re.IGNORECASE
        )
        for match in code_matches:
            props.extend(_extract_property_tokens(match))
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
    one_of: dict[str, list[set[str]]] = {}
    one_of_option_groups: dict[str, list[list[set[str]]]] = {}
    one_of_recommended: dict[str, list[set[str]]] = {}
    one_of_option_groups_recommended: dict[str, list[list[set[str]]]] = {}
    pending_one_of_types: list[str] | None = None
    conditional_required_next_table = False

    for token in TOKEN_RE.findall(html):
        token_lower = token.lower()
        if pending_one_of_types and not token_lower.startswith(("<ul", "<ol")):
            pending_one_of_types = None
        if token_lower.startswith(("<h2", "<h3", "<h4")):
            types = _extract_schema_types(token)
            if types:
                current_types = types
            conditional_required_next_table = False
            continue
        if token_lower.startswith("<p"):
            types = _extract_schema_types(token)
            text = _strip_tags(token).lower()
            if types:
                token_lower_text = token.lower()
                looks_like_markup_example = any(
                    marker in token_lower_text
                    for marker in (
                        "@type",
                        "itemtype=",
                        "typeof=",
                        '"@context"',
                        "<script",
                    )
                )
                is_explicit_type_list = bool(TYPE_LIST_RE.search(text))
                is_full_definition_note = (
                    "full definition of" in text
                    and ("is available" in text or "is provided" in text)
                    and not looks_like_markup_example
                )

                if is_explicit_type_list:
                    current_types = types
                elif is_full_definition_note:
                    overlap = [
                        type_name for type_name in current_types if type_name in types
                    ]
                    current_types = overlap or types
                elif not current_types and looks_like_markup_example:
                    current_types = [types[0]]
            if CONDITIONAL_REQUIRED_RE.search(text):
                conditional_required_next_table = True
            if ONE_OF_RE.search(text) and not ONE_OF_VALUE_RE.search(text):
                pending_one_of_types = current_types or ["Thing"]
            continue

        if token_lower.startswith(("<ul", "<ol")) and pending_one_of_types:
            props = _extract_list_properties(token)
            if props:
                for t in pending_one_of_types:
                    one_of.setdefault(t, []).append(set(props))
            pending_one_of_types = None
            continue

        if token_lower.startswith("<table"):
            kind = _table_kind(token)
            if not kind:
                continue
            if kind == "required" and conditional_required_next_table:
                # Google often phrases scoped requirements as "required when ...".
                # Emit warnings instead of unconditional errors for such sections.
                kind = "recommended"
            conditional_required_next_table = False
            props, groups, option_groups = _extract_table_properties(token)
            if not props and not groups and not option_groups:
                continue
            target_types = current_types or ["Thing"]
            for t in target_types:
                bucket = type_data.setdefault(
                    t, {"required": set(), "recommended": set()}
                )
                bucket[kind].update(props)
                if groups:
                    if kind == "required":
                        one_of.setdefault(t, []).extend(groups)
                    else:
                        one_of_recommended.setdefault(t, []).extend(groups)
                if option_groups:
                    if kind == "required":
                        one_of_option_groups.setdefault(t, []).extend(option_groups)
                    else:
                        one_of_option_groups_recommended.setdefault(t, []).extend(
                            option_groups
                        )

    for t, bucket in type_data.items():
        bucket["recommended"].difference_update(bucket["required"])

    for t, groups in one_of.items():
        bucket = type_data.setdefault(t, {"required": set(), "recommended": set()})
        for group in groups:
            bucket["required"].difference_update(group)
            bucket["recommended"].difference_update(group)

    for t, option_sets in one_of_option_groups.items():
        bucket = type_data.setdefault(t, {"required": set(), "recommended": set()})
        for branches in option_sets:
            for branch in branches:
                bucket["required"].difference_update(branch)
                bucket["recommended"].difference_update(branch)

    for t, groups in one_of_recommended.items():
        bucket = type_data.setdefault(t, {"required": set(), "recommended": set()})
        for group in groups:
            bucket["required"].difference_update(group)
            bucket["recommended"].difference_update(group)

    for t, option_sets in one_of_option_groups_recommended.items():
        bucket = type_data.setdefault(t, {"required": set(), "recommended": set()})
        for branches in option_sets:
            for branch in branches:
                bucket["required"].difference_update(branch)
                bucket["recommended"].difference_update(branch)

    return FeatureData(
        url=url,
        types=type_data,
        one_of=one_of,
        one_of_option_groups=one_of_option_groups,
        one_of_recommended=one_of_recommended,
        one_of_option_groups_recommended=one_of_option_groups_recommended,
    )


def _prop_path(prop: str) -> str:
    parts = prop.split(".")
    if len(parts) == 1:
        return f"schema:{parts[0]}"
    seq = " ".join(f"schema:{part}" for part in parts)
    return f"( {seq} )"


_SCOPED_CHILD_RULES: dict[str, dict[str, list[str]]] = {
    "ItemList": {"itemListElement": ["ListItem"]},
    "BreadcrumbList": {"itemListElement": ["ListItem"]},
    "QAPage": {"mainEntity": ["Question"]},
    "FAQPage": {"mainEntity": ["Question"]},
    "Quiz": {"hasPart": ["Question"]},
    "ProfilePage": {"mainEntity": ["Person", "Organization"]},
    "Question": {
        "acceptedAnswer": ["Answer"],
        "suggestedAnswer": ["Answer"],
        "comment": ["Comment"],
    },
    "Answer": {"comment": ["Comment"]},
    "Product": {
        "offers": ["Offer", "AggregateOffer"],
        "review": ["Review"],
        "aggregateRating": ["AggregateRating"],
    },
    "Recipe": {"recipeInstructions": ["HowToStep"], "step": ["HowToStep"]},
    "Course": {"provider": ["Organization"], "hasPart": ["Course", "CreativeWork"]},
    "Review": {
        "reviewRating": ["Rating"],
        "aggregateRating": ["AggregateRating"],
        "positiveNotes": ["ItemList"],
        "negativeNotes": ["ItemList"],
    },
}


def _emit_property(
    lines: list[str],
    prop: str,
    required: bool,
    child_types: list[str] | None,
    indent: int,
    buckets: dict[str, dict[str, set[str]]],
    visited: set[str],
    one_of_map: dict[str, list[set[str]]],
    one_of_option_map: dict[str, list[list[set[str]]]],
) -> None:
    sp = " " * indent
    path = _prop_path(prop)
    lines.append(f"{sp}sh:property [")
    lines.append(f"{sp}  sh:path {path} ;")
    lines.append(f"{sp}  sh:minCount 1 ;")
    if not required:
        lines.append(f"{sp}  sh:severity sh:Warning ;")
        lines.append(f'{sp}  sh:message "Recommended by Google: {prop}." ;')
    if child_types:
        valid_children = [
            child_type
            for child_type in child_types
            if child_type not in visited and child_type in buckets
        ]
        if len(valid_children) == 1:
            child_type = valid_children[0]
            child_bucket = buckets.get(child_type)
            node_indent = indent + 2
            node_sp = " " * node_indent
            lines.append(f"{node_sp}sh:node [")
            _emit_node(
                lines,
                child_type,
                child_bucket,
                node_indent + 2,
                buckets,
                visited | {child_type},
                one_of_map.get(child_type, []),
                one_of_map,
                one_of_option_map.get(child_type, []),
                one_of_option_map,
            )
            lines.append(f"{node_sp}] ;")
        elif len(valid_children) > 1:
            or_indent = indent + 2
            or_sp = " " * or_indent
            lines.append(f"{or_sp}sh:or (")
            for child_type in valid_children:
                child_bucket = buckets.get(child_type)
                lines.append(f"{or_sp}  [")
                _emit_node(
                    lines,
                    child_type,
                    child_bucket,
                    or_indent + 4,
                    buckets,
                    visited | {child_type},
                    one_of_map.get(child_type, []),
                    one_of_map,
                    one_of_option_map.get(child_type, []),
                    one_of_option_map,
                )
                lines.append(f"{or_sp}  ]")
            lines.append(f"{or_sp}) ;")
    lines.append(f"{sp}] ;")


def _emit_one_of_groups(
    lines: list[str],
    groups: list[set[str]],
    parent_type: str,
    indent: int,
    buckets: dict[str, dict[str, set[str]]],
    visited: set[str],
    one_of_map: dict[str, list[set[str]]],
    one_of_option_map: dict[str, list[list[set[str]]]],
) -> None:
    if not groups:
        return
    sp = " " * indent
    for group in groups:
        if not group:
            continue
        lines.append(f"{sp}sh:or (")
        for prop in sorted(group):
            child_types = _SCOPED_CHILD_RULES.get(parent_type, {}).get(prop)
            lines.append(f"{sp}  [")
            lines.append(f"{sp}    sh:property [")
            lines.append(f"{sp}      sh:path {_prop_path(prop)} ;")
            lines.append(f"{sp}      sh:minCount 1 ;")
            if child_types:
                valid_children = [
                    child_type
                    for child_type in child_types
                    if child_type not in visited and child_type in buckets
                ]
                if len(valid_children) == 1:
                    child_type = valid_children[0]
                    child_bucket = buckets.get(child_type)
                    node_indent = indent + 8
                    node_sp = " " * node_indent
                    lines.append(f"{node_sp}sh:node [")
                    _emit_node(
                        lines,
                        child_type,
                        child_bucket,
                        node_indent + 2,
                        buckets,
                        visited | {child_type},
                        one_of_map.get(child_type, []),
                        one_of_map,
                        one_of_option_map.get(child_type, []),
                        one_of_option_map,
                    )
                    lines.append(f"{node_sp}] ;")
                elif len(valid_children) > 1:
                    or_indent = indent + 8
                    or_sp = " " * or_indent
                    lines.append(f"{or_sp}sh:or (")
                    for child_type in valid_children:
                        child_bucket = buckets.get(child_type)
                        lines.append(f"{or_sp}  [")
                        _emit_node(
                            lines,
                            child_type,
                            child_bucket,
                            or_indent + 4,
                            buckets,
                            visited | {child_type},
                            one_of_map.get(child_type, []),
                            one_of_map,
                            one_of_option_map.get(child_type, []),
                            one_of_option_map,
                        )
                        lines.append(f"{or_sp}  ]")
                    lines.append(f"{or_sp}) ;")
            lines.append(f"{sp}    ] ;")
            lines.append(f"{sp}  ]")
        lines.append(f"{sp}) ;")


def _emit_one_of_option_groups(
    lines: list[str],
    groups: list[list[set[str]]],
    parent_type: str,
    indent: int,
    buckets: dict[str, dict[str, set[str]]],
    visited: set[str],
    one_of_map: dict[str, list[set[str]]],
    one_of_option_map: dict[str, list[list[set[str]]]],
) -> None:
    if not groups:
        return
    sp = " " * indent
    child_rules = _SCOPED_CHILD_RULES.get(parent_type, {})
    for branches in groups:
        if not branches:
            continue
        lines.append(f"{sp}sh:or (")
        for branch in branches:
            if not branch:
                continue
            lines.append(f"{sp}  [")
            for prop in sorted(branch):
                child_types = child_rules.get(prop)
                _emit_property(
                    lines,
                    prop,
                    required=True,
                    child_types=child_types,
                    indent=indent + 4,
                    buckets=buckets,
                    visited=visited,
                    one_of_map=one_of_map,
                    one_of_option_map=one_of_option_map,
                )
            lines.append(f"{sp}  ]")
        lines.append(f"{sp}) ;")


def _emit_listitem_name_or_item_name(lines: list[str], indent: int) -> None:
    sp = " " * indent
    lines.append(f"{sp}sh:or (")
    lines.append(f"{sp}  [")
    lines.append(f"{sp}    sh:property [")
    lines.append(f"{sp}      sh:path schema:name ;")
    lines.append(f"{sp}      sh:minCount 1 ;")
    lines.append(f"{sp}    ] ;")
    lines.append(f"{sp}  ]")
    lines.append(f"{sp}  [")
    lines.append(f"{sp}    sh:property [")
    lines.append(f"{sp}      sh:path schema:item ;")
    lines.append(f"{sp}      sh:node [")
    lines.append(f"{sp}        sh:property [")
    lines.append(f"{sp}          sh:path schema:name ;")
    lines.append(f"{sp}          sh:minCount 1 ;")
    lines.append(f"{sp}        ] ;")
    lines.append(f"{sp}      ] ;")
    lines.append(f"{sp}    ] ;")
    lines.append(f"{sp}  ]")
    lines.append(f"{sp}) ;")


def _emit_node(
    lines: list[str],
    type_name: str,
    bucket: dict[str, set[str]],
    indent: int,
    buckets: dict[str, dict[str, set[str]]],
    visited: set[str],
    one_of_groups: list[set[str]] | None,
    one_of_map: dict[str, list[set[str]]],
    one_of_option_groups: list[list[set[str]]] | None,
    one_of_option_map: dict[str, list[list[set[str]]]],
) -> None:
    sp = " " * indent
    lines.append(f"{sp}a sh:NodeShape ;")
    lines.append(f"{sp}sh:class schema:{type_name} ;")

    child_rules = _SCOPED_CHILD_RULES.get(type_name, {})
    for prop in sorted(bucket["required"]):
        if type_name == "ListItem" and prop == "name":
            # Google: ListItem.name is only required when `item` is a bare URL;
            # if `item` is a Thing that itself carries a name, name may be omitted.
            # https://developers.google.com/search/docs/appearance/structured-data/breadcrumb
            continue
        child_types = child_rules.get(prop)
        _emit_property(
            lines,
            prop,
            required=True,
            child_types=child_types,
            indent=indent,
            buckets=buckets,
            visited=visited,
            one_of_map=one_of_map,
            one_of_option_map=one_of_option_map,
        )
    if type_name == "ListItem" and "name" in bucket["required"]:
        _emit_listitem_name_or_item_name(lines, indent)

    for prop in sorted(bucket["recommended"]):
        child_types = child_rules.get(prop)
        _emit_property(
            lines,
            prop,
            required=False,
            child_types=child_types,
            indent=indent,
            buckets=buckets,
            visited=visited,
            one_of_map=one_of_map,
            one_of_option_map=one_of_option_map,
        )

    _emit_one_of_groups(
        lines,
        one_of_groups or [],
        type_name,
        indent,
        buckets,
        visited,
        one_of_map,
        one_of_option_map,
    )
    _emit_one_of_option_groups(
        lines,
        one_of_option_groups or [],
        type_name,
        indent,
        buckets,
        visited,
        one_of_map,
        one_of_option_map,
    )


def _write_feature(feature: FeatureData, output_path: Path, overwrite: bool) -> bool:
    if output_path.exists() and not overwrite:
        return False

    scoped_types: set[str] = set()
    for parent_type, rules in _SCOPED_CHILD_RULES.items():
        if parent_type not in feature.types:
            continue
        for child_types in rules.values():
            for child_type in child_types:
                if child_type == parent_type:
                    continue
                if child_type in feature.types:
                    scoped_types.add(child_type)

    lines: list[str] = []
    slug = output_path.stem
    prefix_base = f"https://wordlift.io/shacl/google/{slug}/"
    lines.append(f"@prefix : <{prefix_base}> .")
    lines.append("@prefix sh: <http://www.w3.org/ns/shacl#> .")
    lines.append("@prefix schema: <http://schema.org/> .")
    lines.append("")
    lines.append(f"# Source: {feature.url}")
    lines.append(
        "# Generated: "
        f"{datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')}"
    )
    lines.append(
        "# Notes: required properties => errors; recommended properties => warnings."
    )
    lines.append("")

    for type_name in sorted(feature.types.keys()):
        if type_name not in scoped_types:
            bucket = feature.types[type_name]
            shape_name = f":google_{type_name}Shape"
            lines.append(shape_name)
            lines.append("  a sh:NodeShape ;")
            lines.append(f"  sh:targetClass schema:{type_name} ;")

            for prop in sorted(bucket["required"]):
                if type_name == "ListItem" and prop == "name":
                    # Google: ListItem.name is only required when `item` is a bare
                    # URL; if `item` is a Thing that itself carries a name, name
                    # may be omitted. See _emit_listitem_name_or_item_name below.
                    continue
                child_types = _SCOPED_CHILD_RULES.get(type_name, {}).get(prop)
                _emit_property(
                    lines,
                    prop,
                    required=True,
                    child_types=child_types,
                    indent=2,
                    buckets=feature.types,
                    visited={type_name},
                    one_of_map=feature.one_of,
                    one_of_option_map=feature.one_of_option_groups,
                )
            if type_name == "ListItem" and "name" in bucket["required"]:
                _emit_listitem_name_or_item_name(lines, 2)

            for prop in sorted(bucket["recommended"]):
                child_types = _SCOPED_CHILD_RULES.get(type_name, {}).get(prop)
                _emit_property(
                    lines,
                    prop,
                    required=False,
                    child_types=child_types,
                    indent=2,
                    buckets=feature.types,
                    visited={type_name},
                    one_of_map=feature.one_of,
                    one_of_option_map=feature.one_of_option_groups,
                )

            _emit_one_of_groups(
                lines,
                feature.one_of.get(type_name, []),
                type_name,
                2,
                feature.types,
                {type_name},
                feature.one_of,
                feature.one_of_option_groups,
            )
            _emit_one_of_option_groups(
                lines,
                feature.one_of_option_groups.get(type_name, []),
                type_name,
                2,
                feature.types,
                {type_name},
                feature.one_of,
                feature.one_of_option_groups,
            )

            lines.append(".")
            lines.append("")

        recommended_one_of_groups = feature.one_of_recommended.get(type_name, [])
        for idx, group in enumerate(recommended_one_of_groups, start=1):
            shape_name = f":google_{type_name}RecommendedOneOf{idx}Shape"
            lines.append(shape_name)
            lines.append("  a sh:NodeShape ;")
            lines.append(f"  sh:targetClass schema:{type_name} ;")
            lines.append("  sh:severity sh:Warning ;")
            joined = " or ".join(sorted(group))
            lines.append(
                f'  sh:message "Recommended by Google: choose either {joined}." ;'
            )
            _emit_one_of_groups(
                lines,
                [group],
                type_name,
                2,
                feature.types,
                {type_name},
                feature.one_of,
                feature.one_of_option_groups,
            )
            lines.append(".")
            lines.append("")

        recommended_option_groups = feature.one_of_option_groups_recommended.get(
            type_name, []
        )
        for idx, branches in enumerate(recommended_option_groups, start=1):
            shape_name = f":google_{type_name}RecommendedOption{idx}Shape"
            lines.append(shape_name)
            lines.append("  a sh:NodeShape ;")
            lines.append(f"  sh:targetClass schema:{type_name} ;")
            lines.append("  sh:severity sh:Warning ;")
            lines.append(
                '  sh:message "Recommended by Google: satisfy one of the documented option branches." ;'
            )
            _emit_one_of_option_groups(
                lines,
                [branches],
                type_name,
                2,
                feature.types,
                {type_name},
                feature.one_of,
                feature.one_of_option_groups,
            )
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


def _canonical_schema_uri(uri: URIRef) -> URIRef | None:
    value = str(uri)
    for namespace in (str(SCHEMA_VOCAB), str(SCHEMA_DATA)):
        if value.startswith(namespace):
            return URIRef(f"{SCHEMA_DATA}{value[len(namespace) :]}")
    return None


def _schema_subclass_edges(graph: Graph) -> set[tuple[URIRef, URIRef]]:
    edges: set[tuple[URIRef, URIRef]] = set()
    for child, parent in graph.subject_objects(RDFS.subClassOf):
        if not isinstance(child, URIRef) or not isinstance(parent, URIRef):
            continue
        canonical_child = _canonical_schema_uri(child)
        canonical_parent = _canonical_schema_uri(parent)
        if canonical_child is not None and canonical_parent is not None:
            edges.add((canonical_child, canonical_parent))
    return edges


def _render_domain_rule(
    prop: URIRef,
    domains: Iterable[URIRef],
) -> list[str]:
    short_prop = _short_name(prop)
    domain_names = sorted(
        {
            _short_name(canonical)
            for domain in domains
            if (canonical := _canonical_schema_uri(domain)) is not None
        }
    )
    if not domain_names:
        return []

    lines = [
        f":schema_{short_prop}DomainRule",
        "  a :PropertyDomainRule ;",
        f"  :path schema:{short_prop} ;",
    ]
    for index, name in enumerate(domain_names):
        suffix = "," if index < len(domain_names) - 1 else " ."
        predicate = "  :domain" if index == 0 else "          "
        lines.append(f"{predicate} schema:{name}{suffix}")
    return lines


def _load_schema_graph() -> Graph:
    response = requests.get(SCHEMA_JSONLD_URL, timeout=60)
    response.raise_for_status()
    graph = Graph()
    graph.parse(data=response.text, format="json-ld")
    return graph


def _write_subclass_ontology(
    output_path: Path,
    subclass_edges: set[tuple[URIRef, URIRef]],
) -> None:
    predicate = str(RDFS.subClassOf)
    lines = [
        f"<{child}> <{predicate}> <{parent}> ."
        for child, parent in sorted(
            subclass_edges, key=lambda edge: tuple(map(str, edge))
        )
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _render_property_shape(prop: URIRef, ranges: list[URIRef]) -> list[str]:
    lines: list[str] = []
    lines.append("  sh:property [")
    lines.append(f"    sh:path schema:{_short_name(prop)} ;")
    lines.append("    sh:severity sh:Warning ;")

    range_constraints: list[str] = []
    range_constraints.append(f"[ sh:datatype <{XSD.anyURI}> ]")
    range_constraints.append(f"[ sh:datatype <{XSD.string}> ]")
    range_constraints.append(f"[ sh:datatype <{RDF_NS.langString}> ]")
    for r in ranges:
        name = _short_name(r)
        datatype_shapes = _datatype_shapes(name)
        if datatype_shapes:
            for shape in datatype_shapes:
                range_constraints.append(f"[ sh:datatype <{shape['datatype']}> ]")
        else:
            range_constraints.append(f"[ sh:class schema:{name} ]")

    if range_constraints:
        range_constraints = _unique(range_constraints)
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


def generate_schema_shacls(
    output_file: Path,
    overwrite: bool,
    ontology_output_file: Path | None = None,
) -> int:
    output_path = output_file
    ontology_output_path = ontology_output_file or output_path.with_name(
        "schemaorg-subclass-ontology.nt"
    )
    if output_path.exists() and not overwrite:
        print(f"Output exists: {output_path}")
        return 1
    if ontology_output_path.exists() and not overwrite:
        print(f"Output exists: {ontology_output_path}")
        return 1

    graph = _load_schema_graph()

    classes = _collect_classes(graph)
    props = _collect_properties(graph)
    subclass_edges = _schema_subclass_edges(graph)

    class_props: dict[URIRef, list[PropertyRange]] = {cls: [] for cls in classes}
    property_domains: dict[URIRef, set[URIRef]] = {}

    for prop in tqdm(props, desc="Collecting properties", unit="prop"):
        for domain, ranges in _collect_domain_ranges(graph, prop):
            property_domains.setdefault(prop, set()).add(domain)
            if domain not in class_props:
                class_props[domain] = []
            class_props[domain].append(PropertyRange(prop=prop, ranges=ranges))

    lines: list[str] = []
    lines.append("@prefix : <https://wordlift.io/shacl/schemaorg-grammar/> .")
    lines.append(f"@prefix sh: <{SH}> .")
    lines.append(f"@prefix schema: <{SCHEMA_DATA}> .")
    lines.append("")
    lines.append(f"# Source: {SCHEMA_JSONLD_URL}")
    lines.append(
        "# Generated: "
        f"{datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')}"
    )
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

    for prop in tqdm(props, desc="Writing domain checks", unit="prop"):
        domain_lines = _render_domain_rule(
            prop,
            property_domains.get(prop, set()),
        )
        if not domain_lines:
            continue
        lines.extend(domain_lines)
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    _write_subclass_ontology(ontology_output_path, subclass_edges)
    print(f"Wrote {output_path}")
    print(f"Wrote {ontology_output_path}")
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
    parser.add_argument(
        "--ontology-output-file",
        help=(
            "Output Schema.org subclass ontology file. Defaults to "
            "schemaorg-subclass-ontology.nt beside --output-file."
        ),
    )
    args = parser.parse_args(argv)
    return generate_schema_shacls(
        Path(args.output_file),
        args.overwrite,
        ontology_output_file=Path(args.ontology_output_file)
        if args.ontology_output_file
        else None,
    )


def _gs1_short_name(uri: URIRef) -> str:
    value = str(uri)
    if value.startswith(str(GS1_NS)):
        return value[len(str(GS1_NS)) :]
    return value.rsplit("/", 1)[-1]


def _collect_gs1_classes(graph: Graph) -> list[URIRef]:
    classes: set[URIRef] = set()
    for cls in graph.subjects(RDF.type, OWL_NS.Class):
        if isinstance(cls, URIRef) and str(cls).startswith(str(GS1_NS)):
            classes.add(cls)
    for cls in graph.subjects(RDF.type, RDFS.Class):
        if isinstance(cls, URIRef) and str(cls).startswith(str(GS1_NS)):
            classes.add(cls)
    return sorted(classes, key=str)


def _collect_gs1_properties(graph: Graph) -> list[URIRef]:
    props: set[URIRef] = set()
    for prop in graph.subjects(RDF.type, RDF.Property):
        if isinstance(prop, URIRef) and str(prop).startswith(str(GS1_NS)):
            props.add(prop)
    return sorted(props, key=str)


def _collect_gs1_domain_ranges(
    graph: Graph, prop: URIRef
) -> list[tuple[URIRef, list[URIRef]]]:
    domain_nodes = list(graph.objects(prop, RDFS.domain))
    ranges = [r for r in graph.objects(prop, RDFS.range) if isinstance(r, URIRef)]

    domains: list[URIRef] = []
    for d in domain_nodes:
        if isinstance(d, URIRef):
            domains.append(d)
        else:
            # Blank node: check for owl:unionOf (union class)
            union_list = list(graph.objects(d, OWL_NS.unionOf))
            if union_list:
                for member in Collection(graph, union_list[0]):
                    if isinstance(member, URIRef):
                        domains.append(member)

    if not domains:
        return []
    return [(domain, ranges) for domain in domains]


def _render_gs1_property_shape(prop: URIRef, ranges: list[URIRef]) -> list[str]:
    lines: list[str] = []
    lines.append("  sh:property [")
    short = _gs1_short_name(prop)
    lines.append(f"    sh:path gs1:{short} ;")
    lines.append("    sh:severity sh:Warning ;")

    range_constraints: list[str] = []
    for r in ranges:
        r_str = str(r)
        if r_str.startswith(str(XSD)) or r_str == str(RDF_NS.langString):
            range_constraints.append(f"[ sh:datatype <{r_str}> ]")
        elif r_str.startswith(str(GS1_NS)):
            range_constraints.append(f"[ sh:class gs1:{_gs1_short_name(r)} ]")
        else:
            range_constraints.append(f"[ sh:datatype <{r_str}> ]")

    if range_constraints:
        range_constraints = _unique(range_constraints)
        if len(range_constraints) == 1:
            lines.append(f"    sh:or ( {range_constraints[0]} ) ;")
        else:
            lines.append("    sh:or (")
            for rc in range_constraints:
                lines.append(f"      {rc}")
            lines.append("    ) ;")

    lines.append(f'    sh:message "GS1 range check: {short}." ;')
    lines.append("  ] ;")
    return lines


def generate_gs1_shacls(output_file: Path, overwrite: bool) -> int:
    output_path = output_file
    if output_path.exists() and not overwrite:
        print(f"Output exists: {output_path}")
        return 1

    response = requests.get(GS1_VOC_URL, timeout=60)
    response.raise_for_status()

    graph = Graph()
    graph.parse(data=response.text, format="turtle")

    classes = _collect_gs1_classes(graph)
    all_props = _collect_gs1_properties(graph)

    class_props: dict[URIRef, list[PropertyRange]] = {cls: [] for cls in classes}

    for prop in tqdm(all_props, desc="Collecting GS1 properties", unit="prop"):
        for domain, ranges in _collect_gs1_domain_ranges(graph, prop):
            if domain not in class_props:
                class_props[domain] = []
            class_props[domain].append(PropertyRange(prop=prop, ranges=ranges))

    lines: list[str] = []
    lines.append("@prefix : <https://wordlift.io/shacl/gs1-grammar/> .")
    lines.append(f"@prefix sh: <{SH}> .")
    lines.append(f"@prefix gs1: <{GS1_NS}> .")
    lines.append(f"@prefix xsd: <{XSD}> .")
    lines.append("")
    lines.append(f"# Source: {GS1_VOC_URL}")
    lines.append(
        "# Generated: "
        f"{datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')}"
    )
    lines.append(
        "# Notes: GS1 vocabulary grammar checks only; all constraints are warnings."
    )
    lines.append("")

    for cls in tqdm(classes, desc="Writing GS1 shapes", unit="class"):
        props_for_class = class_props.get(cls, [])
        if not props_for_class:
            continue
        short = _gs1_short_name(cls)
        shape_name = f":gs1_{short}Shape"
        lines.append(shape_name)
        lines.append("  a sh:NodeShape ;")
        lines.append(f"  sh:targetClass gs1:{short} ;")

        for prop_range in props_for_class:
            lines.extend(_render_gs1_property_shape(prop_range.prop, prop_range.ranges))

        lines.append(".")
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


def gs1_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate GS1 vocabulary grammar SHACLs."
    )
    parser.add_argument(
        "--output-file",
        default="wordlift_sdk/validation/shacls/gs1-grammar.ttl",
        help="Output SHACL file.",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing file."
    )
    args = parser.parse_args(argv)
    return generate_gs1_shacls(Path(args.output_file), args.overwrite)


JSONLD_META_TOKEN_BLACKLIST = {"context", "type", "id", "graph"}
