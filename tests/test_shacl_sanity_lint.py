from __future__ import annotations

import re
from pathlib import Path


SHAPES_DIR = Path("wordlift_sdk/validation/shacls")
SCHEMA_GRAMMAR_PATH = SHAPES_DIR / "schemaorg-grammar.ttl"

PATH_PROP_RE = re.compile(r"sh:path\s+(?:\(\s*)?schema:([A-Za-z][A-Za-z0-9]*)")
TARGET_CLASS_RE = re.compile(r"sh:targetClass\s+schema:[A-Za-z][A-Za-z0-9]*")
KNOWN_GOOGLE_PSEUDO_PROPERTIES = {"input", "xPath"}


def _schema_property_names() -> set[str]:
    text = SCHEMA_GRAMMAR_PATH.read_text(encoding="utf-8")
    return set(PATH_PROP_RE.findall(text))


def _google_shape_paths() -> list[Path]:
    return sorted(
        path
        for path in SHAPES_DIR.glob("google-*.ttl")
        if path.is_file() and path.name != "schemaorg-grammar.ttl"
    )


def test_google_shacls_have_target_classes() -> None:
    for shape_path in _google_shape_paths():
        text = shape_path.read_text(encoding="utf-8")
        assert TARGET_CLASS_RE.search(text), f"Missing targetClass in {shape_path}"


def test_google_shacl_paths_use_known_schema_properties() -> None:
    known_props = _schema_property_names()
    assert known_props, "Failed to load schema.org property names from grammar shape."

    for shape_path in _google_shape_paths():
        text = shape_path.read_text(encoding="utf-8")
        used_props = set(PATH_PROP_RE.findall(text))
        unknown = sorted(
            prop
            for prop in used_props
            if prop not in known_props and prop not in KNOWN_GOOGLE_PSEUDO_PROPERTIES
        )
        assert not unknown, (
            f"Unknown schema properties in {shape_path}: {unknown}. "
            "Likely parser extraction noise."
        )
