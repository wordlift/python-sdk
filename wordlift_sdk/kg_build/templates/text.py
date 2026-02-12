from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Mapping

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

    def load_exports(
        self, directory: Path, context: Mapping[str, Any]
    ) -> dict[str, Any]:
        candidates = (
            directory / "exports.toml",
            directory / "exports.toml.j2",
            directory / "exports.toml.liquid",
        )
        for path in candidates:
            if not path.exists():
                continue
            rendered = self.render_file(path, context)
            data = tomllib.loads(rendered)
            if not isinstance(data, dict):
                raise ValueError(f"Invalid exports manifest: {path}")
            return data
        return {}

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
