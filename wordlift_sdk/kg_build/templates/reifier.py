from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from jinja2 import Environment, StrictUndefined
from liquid import Environment as LiquidEnvironment
from liquid.undefined import StrictUndefined as LiquidStrictUndefined
from rdflib import Graph
from rdflib.util import guess_format


class JinjaRdfTemplateReifier:
    """Render RDF templates (`*.j2`, `*.liquid`, or static RDF files) into one graph."""

    def __init__(self, template_dirs: Path | Sequence[Path]) -> None:
        if isinstance(template_dirs, Path):
            self._template_dirs = (template_dirs,)
        else:
            self._template_dirs = tuple(template_dirs)
        self._jinja = Environment(
            autoescape=False,
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )
        self._liquid = LiquidEnvironment(undefined=LiquidStrictUndefined)

    def has_templates(self) -> bool:
        paths, _summary = self.resolve_template_paths()
        return len(paths) > 0

    def resolve_template_paths(self) -> tuple[list[Path], dict[str, int]]:
        resolved: dict[Path, Path] = {}
        overrides = 0
        source_files = 0
        for template_dir in self._template_dirs:
            if not template_dir.exists():
                continue
            files = sorted(path for path in template_dir.rglob("*") if path.is_file())
            source_files += len(files)
            for path in files:
                rel = path.relative_to(template_dir)
                if rel in resolved:
                    overrides += 1
                resolved[rel] = path

        effective_paths = [resolved[k] for k in sorted(resolved, key=lambda p: str(p))]
        return effective_paths, {
            "source_files": source_files,
            "effective_files": len(effective_paths),
            "overrides": overrides,
        }

    @staticmethod
    def _infer_rdf_format(path: Path) -> str | None:
        if path.suffix in {".j2", ".liquid"}:
            # Guess format from filename before the template extension
            # (e.g. `entity.ttl.j2` or `entity.jsonld.liquid`).
            return guess_format(path.with_suffix("").name)
        return guess_format(path.name)

    def reify(self, context: Mapping[str, Any]) -> Graph:
        graph = Graph()
        template_paths, _summary = self.resolve_template_paths()
        if not template_paths:
            return graph

        resolved_context = dict(context)
        dataset_uri = resolved_context.get("dataset_uri")
        if not dataset_uri:
            account = resolved_context.get("account")
            dataset_uri = getattr(account, "dataset_uri", None) if account else None

        if not dataset_uri:
            raise ValueError(
                "Template reifier requires dataset_uri in context/account."
            )

        resolved_context["dataset_uri"] = str(dataset_uri).rstrip("/")

        for template_path in template_paths:
            rdf_format = self._infer_rdf_format(template_path)
            if rdf_format is None:
                continue

            template_source = template_path.read_text(encoding="utf-8")
            if template_path.suffix == ".j2":
                template = self._jinja.from_string(template_source)
                rendered = template.render(**resolved_context)
            elif template_path.suffix == ".liquid":
                template = self._liquid.from_string(template_source)
                rendered = template.render(**resolved_context)
            else:
                rendered = template_source

            graph.parse(data=rendered, format=rdf_format)

        return graph
