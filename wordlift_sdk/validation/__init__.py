"""Validation utilities."""

from __future__ import annotations

from .._lazy_exports import resolve_attr

__all__ = [
    "PreparedShaclValidator",
    "PreparedShapes",
    "PreparedValidationResult",
    "ValidationIssue",
    "ValidationResult",
    "assign_stable_jsonld_ids",
    "extract_validation_issues",
    "filter_validation_issues",
    "list_shape_names",
    "resolve_shape_specs",
    "prepare_shapes",
    "validate_file",
    "validate_jsonld_from_url",
    "ShaclValidationService",
    "ValidationMode",
    "ValidationOutcome",
]


_EXPORTS = {
    "PreparedShaclValidator": (
        "wordlift_sdk.validation.shacl",
        "PreparedShaclValidator",
    ),
    "PreparedShapes": ("wordlift_sdk.validation.shacl", "PreparedShapes"),
    "PreparedValidationResult": (
        "wordlift_sdk.validation.shacl",
        "PreparedValidationResult",
    ),
    "ValidationIssue": ("wordlift_sdk.validation.shacl", "ValidationIssue"),
    "ValidationResult": ("wordlift_sdk.validation.shacl", "ValidationResult"),
    "assign_stable_jsonld_ids": (
        "wordlift_sdk.validation.shacl",
        "assign_stable_jsonld_ids",
    ),
    "extract_validation_issues": (
        "wordlift_sdk.validation.shacl",
        "extract_validation_issues",
    ),
    "filter_validation_issues": (
        "wordlift_sdk.validation.shacl",
        "filter_validation_issues",
    ),
    "list_shape_names": ("wordlift_sdk.validation.shacl", "list_shape_names"),
    "resolve_shape_specs": (
        "wordlift_sdk.validation.shacl",
        "resolve_shape_specs",
    ),
    "prepare_shapes": ("wordlift_sdk.validation.shacl", "prepare_shapes"),
    "validate_file": ("wordlift_sdk.validation.shacl", "validate_file"),
    "validate_jsonld_from_url": (
        "wordlift_sdk.validation.shacl",
        "validate_jsonld_from_url",
    ),
    "ShaclValidationService": (
        "wordlift_sdk.validation.shacl_validation_service",
        "ShaclValidationService",
    ),
    "ValidationMode": (
        "wordlift_sdk.validation.shacl_validation_service",
        "ValidationMode",
    ),
    "ValidationOutcome": (
        "wordlift_sdk.validation.shacl_validation_service",
        "ValidationOutcome",
    ),
}


def __getattr__(name: str):
    return resolve_attr(
        name=name,
        module_name="wordlift_sdk.validation",
        exports=_EXPORTS,
        extra="validation",
    )
