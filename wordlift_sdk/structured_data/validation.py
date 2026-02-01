"""SHACL validation helpers."""

from __future__ import annotations

import json
from pathlib import Path

from wordlift_sdk.structured_data.schema_guide import SchemaGuide
from wordlift_sdk.validation.shacl import validate_file


class ValidationService:
    """Validates JSON-LD outputs with SHACL shapes."""

    def __init__(self, schema: SchemaGuide | None = None) -> None:
        self._schema = schema or SchemaGuide()

    def validate(self, jsonld_path: Path, target_type: str, workdir: Path) -> str:
        shape_specs = self._schema.shape_specs_for_type(target_type)
        result = validate_file(str(jsonld_path), shape_specs=shape_specs)
        (workdir / "jsonld.validation.json").write_text(
            json.dumps(
                {
                    "conforms": result.conforms,
                    "warning_count": result.warning_count,
                    "report_text": result.report_text,
                },
                indent=2,
            )
        )
        return result.report_text
