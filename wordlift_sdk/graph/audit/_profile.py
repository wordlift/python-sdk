"""Resolve SHACL shape specs from a ProfileDefinition."""

from __future__ import annotations

from wordlift_sdk.kg_build.config import ProfileDefinition
from wordlift_sdk.validation.shacl import resolve_shape_specs


def shape_specs_for_profile(
    profile: ProfileDefinition | None,
    *,
    builtin_shapes: list[str] | None = None,
    exclude_builtin_shapes: list[str] | None = None,
    extra_shapes: list[str] | None = None,
) -> list[str]:
    """
    Return the ordered list of SHACL shape specs.

    Explicit keyword arguments take precedence over values from *profile*
    settings.  Falls back to the default built-in set when neither explicit
    values nor profile settings are present.
    """
    settings = profile.settings if profile is not None else {}
    return resolve_shape_specs(
        builtin_shapes=builtin_shapes
        if builtin_shapes is not None
        else settings.get("shacl_builtin_shapes"),
        exclude_builtin_shapes=exclude_builtin_shapes
        if exclude_builtin_shapes is not None
        else settings.get("shacl_exclude_builtin_shapes"),
        extra_shapes=extra_shapes
        if extra_shapes is not None
        else settings.get("shacl_extra_shapes"),
    )


__all__ = ["shape_specs_for_profile"]
