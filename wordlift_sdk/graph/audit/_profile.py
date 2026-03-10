"""Resolve SHACL shape specs from a ProfileDefinition."""

from __future__ import annotations

from wordlift_sdk.kg_build.config import ProfileDefinition
from wordlift_sdk.validation.shacl import resolve_shape_specs


def shape_specs_for_profile(profile: ProfileDefinition | None) -> list[str]:
    """
    Return the ordered list of SHACL shape specs to use for a given profile.

    Falls back to the default built-in set when *profile* is ``None`` or
    when the profile settings contain no SHACL keys.
    """
    if profile is None:
        return resolve_shape_specs()

    settings = profile.settings
    return resolve_shape_specs(
        builtin_shapes=settings.get("shacl_builtin_shapes"),
        exclude_builtin_shapes=settings.get("shacl_exclude_builtin_shapes"),
        extra_shapes=settings.get("shacl_extra_shapes"),
    )


__all__ = ["shape_specs_for_profile"]
