"""Validation utilities."""

from __future__ import annotations

from .shacl import (
    ValidationIssue,
    ValidationResult,
    extract_validation_issues,
    filter_validation_issues,
    list_shape_names,
    resolve_shape_specs,
    validate_file,
    validate_jsonld_from_url,
)

__all__ = [
    "ValidationIssue",
    "ValidationResult",
    "extract_validation_issues",
    "filter_validation_issues",
    "list_shape_names",
    "resolve_shape_specs",
    "validate_file",
    "validate_jsonld_from_url",
]
