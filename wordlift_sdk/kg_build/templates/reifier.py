from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from jinja2 import Environment, StrictUndefined
from liquid import Environment as LiquidEnvironment
from liquid.undefined import StrictUndefined as LiquidStrictUndefined
from rdflib import Graph
from rdflib.util import guess_format


class JinjaRdfTemplateReifier:
    """Render RDF templates (`*.j2`, `*.liquid`, or static RDF files) into one graph."""

    def __init__(self, template_dir: Path) -> None:
        self._template_dir = template_dir
        self._jinja = Environment(
            autoescape=False,
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )
        self._liquid = LiquidEnvironment(undefined=LiquidStrictUndefined)

    def has_templates(self) -> bool:
        return self._template_dir.exists() and any(self._iter_template_paths())

    def _iter_template_paths(self) -> list[Path]:
        if not self._template_dir.exists():
            return []
        return sorted(path for path in self._template_dir.iterdir() if path.is_file())

    @staticmethod
    def _infer_rdf_format(path: Path) -> str | None:
        if path.suffix in {".j2", ".liquid"}:
            # Guess format from filename before the template extension
            # (e.g. `entity.ttl.j2` or `entity.jsonld.liquid`).
            return guess_format(path.with_suffix("").name)
        return guess_format(path.name)

    def reify(self, context: Mapping[str, Any]) -> Graph:
        graph = Graph()
        if not self._template_dir.exists():
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

        for template_path in self._iter_template_paths():
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
