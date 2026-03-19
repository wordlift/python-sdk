from __future__ import annotations

import logging
from pathlib import Path

from .graph_io import close_loaded_postprocessors
from .subprocess import (
    _build_handler,
    _normalize_runtime,
)
from .types import (
    Closeable,
    GraphPostprocessor,
    LoadedPostprocessor,
    PostprocessorContext,
    PostprocessorResult,
    PostprocessorRuntime,
    PostprocessorSpec,
    PersistentWorkerJobError,
    PersistentWorkerTransportError,
)

logger = logging.getLogger(__name__)

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


def _as_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise TypeError("Expected boolean value.")


def _as_str(value, default: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str) or not value.strip():
        raise TypeError("Expected non-empty string value.")
    return value


def _as_positive_int(value, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or value <= 0:
        raise TypeError("Expected positive integer value.")
    return value


def _load_manifest_specs(manifest_path: Path) -> list[PostprocessorSpec]:
    if not manifest_path.exists():
        return []
    with open(manifest_path, "rb") as f:
        doc = tomllib.load(f)

    default_python = _as_str(doc.get("python"), "./.venv/bin/python")
    default_timeout = _as_positive_int(doc.get("timeout_seconds"), 120)
    default_enabled = _as_bool(doc.get("enabled"), True)
    default_keep_temp = _as_bool(doc.get("keep_temp_on_error"), False)

    rows = doc.get("postprocessors")
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise TypeError(
            f"{manifest_path}: 'postprocessors' must be an array of tables."
        )

    specs: list[PostprocessorSpec] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise TypeError(
                f"{manifest_path}: postprocessors[{index}] must be a table."
            )
        class_path = row.get("class")
        if not isinstance(class_path, str) or ":" not in class_path:
            raise TypeError(
                f"{manifest_path}: postprocessors[{index}].class must be "
                "'package.module:ClassName'."
            )
        specs.append(PostprocessorSpec(
            class_path=class_path.strip(),
            python=_as_str(row.get("python"), default_python),
            timeout_seconds=_as_positive_int(row.get("timeout_seconds"), default_timeout),
            enabled=_as_bool(row.get("enabled"), default_enabled),
            keep_temp_on_error=_as_bool(row.get("keep_temp_on_error"), default_keep_temp),
        ))
    return specs


def _load_from_specs(
    specs: list[PostprocessorSpec],
    root_dir: Path,
    runtime: PostprocessorRuntime,
) -> list[LoadedPostprocessor]:
    return [
        LoadedPostprocessor(
            name=spec.class_path,
            handler=_build_handler(spec, root_dir, runtime),
        )
        for spec in specs
        if spec.enabled
    ]


def load_postprocessors_for_profile(
    *,
    root_dir: Path,
    profile_name: str,
    runtime: str | None = None,
) -> list[LoadedPostprocessor]:
    base_manifest = root_dir / "profiles" / "_base" / "postprocessors.toml"
    profile_manifest = root_dir / "profiles" / profile_name / "postprocessors.toml"

    if profile_manifest.exists():
        selected_manifest: Path | None = profile_manifest
    elif base_manifest.exists():
        selected_manifest = base_manifest
    else:
        selected_manifest = None

    logger.debug(
        "Postprocessor manifest precedence for profile '%s': profile=%s base=%s chosen=%s",
        profile_name,
        profile_manifest,
        base_manifest,
        selected_manifest or "none",
    )
    return load_postprocessors(selected_manifest, root_dir=root_dir, runtime=runtime)


def load_postprocessors(
    manifest_path: Path | None,
    *,
    root_dir: Path,
    runtime: str | None = None,
) -> list[LoadedPostprocessor]:
    specs = _load_manifest_specs(manifest_path) if manifest_path else []
    resolved_runtime = _normalize_runtime(runtime)
    loaded = _load_from_specs(specs, root_dir, resolved_runtime)
    logger.info(
        "Loaded %s postprocessors from manifest: %s (runtime=%s)",
        len(loaded),
        manifest_path or "none",
        resolved_runtime,
    )
    return loaded


__all__ = [
    "Closeable",
    "GraphPostprocessor",
    "LoadedPostprocessor",
    "PostprocessorContext",
    "PostprocessorResult",
    "PostprocessorRuntime",
    "PostprocessorSpec",
    "PersistentWorkerJobError",
    "PersistentWorkerTransportError",
    "close_loaded_postprocessors",
    "load_postprocessors",
    "load_postprocessors_for_profile",
]
