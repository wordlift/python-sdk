"""Validation utilities."""

from __future__ import annotations

from .shacl import (
    ValidationResult,
    list_shape_names,
    validate_file,
    validate_jsonld_from_url,
)

__all__ = [
    "ValidationResult",
    "list_shape_names",
    "validate_file",
    "validate_jsonld_from_url",
]
