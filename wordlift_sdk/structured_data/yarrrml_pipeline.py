"""YARRRML to JSON-LD pipeline helpers."""

from __future__ import annotations

from .engine import (
    build_output_basename,
    ensure_no_blank_nodes,
    make_reusable_yarrrml,
    materialize_yarrrml_jsonld,
    normalize_yarrrml_mappings,
    postprocess_jsonld,
)


class YarrrmlPipeline:
    """YARRRML -> JSON-LD pipeline helpers."""

    def normalize_mappings(self, *args, **kwargs):
        return normalize_yarrrml_mappings(*args, **kwargs)

    def materialize_jsonld(self, *args, **kwargs):
        return materialize_yarrrml_jsonld(*args, **kwargs)

    def postprocess_jsonld(self, *args, **kwargs):
        return postprocess_jsonld(*args, **kwargs)

    def ensure_no_blank_nodes(self, *args, **kwargs):
        return ensure_no_blank_nodes(*args, **kwargs)

    def make_reusable_yarrrml(self, *args, **kwargs):
        return make_reusable_yarrrml(*args, **kwargs)

    def build_output_basename(self, *args, **kwargs):
        return build_output_basename(*args, **kwargs)
