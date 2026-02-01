"""Schema.org shape and property guidance."""

from __future__ import annotations

from .engine import normalize_type, shape_specs_for_type


class SchemaGuide:
    """Builds schema.org property guides and shape specs."""

    def normalize_type(self, value: str) -> str:
        return normalize_type(value)

    def shape_specs_for_type(self, type_name: str | None) -> list[str]:
        if not type_name:
            return []
        return shape_specs_for_type(type_name)
