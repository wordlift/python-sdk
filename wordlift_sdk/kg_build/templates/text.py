from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Mapping, Sequence

from jinja2 import Environment, StrictUndefined
from liquid import Environment as LiquidEnvironment
from liquid.undefined import StrictUndefined as LiquidStrictUndefined


class TemplateTextRenderer:
    def __init__(self) -> None:
        self._jinja = Environment(
            autoescape=False,
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )
        self._liquid = LiquidEnvironment(undefined=LiquidStrictUndefined)

    def render_file(self, path: Path, context: Mapping[str, Any]) -> str:
        source = path.read_text(encoding="utf-8")
        if path.suffix == ".j2":
            return self._jinja.from_string(source).render(**context)
        if path.suffix == ".liquid":
            return self._liquid.from_string(source).render(**context)
        return source

    def _coerce_directories(
        self, directories: Path | Sequence[Path]
    ) -> tuple[Path, ...]:
        if isinstance(directories, Path):
            return (directories,)
        return tuple(directories)

    @staticmethod
    def _exports_candidates(directory: Path) -> tuple[Path, ...]:
        files = ("exports.toml", "exports.toml.j2", "exports.toml.liquid")
        candidates: list[Path] = []
        seen: set[Path] = set()

        roots = [directory]
        if directory.name == "templates":
            roots.insert(0, directory.parent)

        for root in roots:
            for filename in files:
                candidate = root / filename
                if candidate in seen:
                    continue
                seen.add(candidate)
                candidates.append(candidate)

        return tuple(candidates)

    def _load_exports_for_directory(
        self, directory: Path, context: Mapping[str, Any]
    ) -> tuple[dict[str, Any], Path | None, tuple[Path, ...]]:
        candidates = self._exports_candidates(directory)
        for path in candidates:
            if not path.exists():
                continue
            rendered = self.render_file(path, context)
            data = tomllib.loads(rendered)
            if not isinstance(data, dict):
                raise ValueError(f"Invalid exports manifest: {path}")
            return data, path, candidates
        return {}, None, candidates

    def load_exports(
        self, directories: Path | Sequence[Path], context: Mapping[str, Any]
    ) -> dict[str, Any]:
        exports, _summary = self.load_exports_with_summary(directories, context)
        return exports

    def load_exports_with_summary(
        self, directories: Path | Sequence[Path], context: Mapping[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        merged: dict[str, Any] = {}
        overrides = 0
        source_keys = 0
        searched_paths: list[str] = []
        loaded_files: list[str] = []
        seen_search_paths: set[str] = set()
        for directory in self._coerce_directories(directories):
            current, loaded_path, candidates = self._load_exports_for_directory(
                directory, context
            )
            for candidate in candidates:
                candidate_str = str(candidate)
                if candidate_str in seen_search_paths:
                    continue
                seen_search_paths.add(candidate_str)
                searched_paths.append(candidate_str)
            if loaded_path is not None:
                loaded_files.append(str(loaded_path))
            source_keys += len(current)
            for key, value in current.items():
                if key in merged:
                    overrides += 1
                merged[key] = value
        return merged, {
            "source_keys": source_keys,
            "effective_keys": len(merged),
            "overrides": overrides,
            "searched_paths": searched_paths,
            "loaded_files": loaded_files,
        }

    @staticmethod
    def resolve_mapping_template(path: Path) -> Path:
        if path.suffix in {".j2", ".liquid"} and path.exists():
            return path
        j2 = path.with_name(path.name + ".j2")
        if j2.exists():
            return j2
        liquid = path.with_name(path.name + ".liquid")
        if liquid.exists():
            return liquid
        return path
