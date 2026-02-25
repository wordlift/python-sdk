from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from rdflib import Graph
from wordlift_sdk.protocol import Context
from wordlift_sdk.structured_data.materialization import MaterializationPipeline
from wordlift_sdk.utils.html_converter import HtmlConverter

logger = logging.getLogger(__name__)


class RmlMappingService:
    def __init__(self, context: Context) -> None:
        self._context = context
        self._html_converter = HtmlConverter()

    def to_xhtml(self, html: str) -> str:
        return self._html_converter.convert(html)

    async def apply_mapping(
        self,
        html: str,
        url: str,
        mapping_file_path: str | Path,
        xhtml: str | None = None,
        mapping_content: str | None = None,
        response: object | None = None,
        debug_output: dict[str, str] | None = None,
    ) -> Graph | None:
        try:
            xhtml_str = xhtml or self.to_xhtml(html)
            if debug_output is not None:
                debug_output["xhtml"] = xhtml_str

            with tempfile.TemporaryDirectory() as temp_dir:
                data_path = os.path.join(temp_dir, "data.xhtml")
                with open(data_path, "w", encoding="utf-8") as f:
                    f.write(xhtml_str)

                resolved_mapping_content = mapping_content
                if resolved_mapping_content is None:
                    try:
                        with open(mapping_file_path, "r", encoding="utf-8") as f:
                            resolved_mapping_content = f.read()
                    except FileNotFoundError:
                        logger.error("Mapping file not found: %s", mapping_file_path)
                        return None

                dataset_uri = getattr(self._context.account, "dataset_uri", None)
                if not dataset_uri:
                    raise RuntimeError("Dataset URI not available on context.account.")

                pipeline = MaterializationPipeline()
                normalized_yarrrml, mappings = pipeline.normalize(
                    resolved_mapping_content,
                    url,
                    Path(data_path),
                    response=response,
                )
                jsonld_raw = pipeline.materialize(
                    normalized_yarrrml,
                    Path(data_path),
                    Path(temp_dir),
                    url=url,
                    response=response,
                )
                jsonld_data = pipeline.postprocess(
                    jsonld_raw,
                    mappings,
                    xhtml_str,
                    dataset_uri,
                    url,
                )
                jsonld_data = self._normalize_schema_uris(jsonld_data)
                jsonld_payload = json.dumps(jsonld_data)
                graph = Graph()
                graph.parse(data=jsonld_payload, format="json-ld")

                if len(graph) > 0:
                    logger.info(
                        "Generated %s triples from mapping %s.",
                        len(graph),
                        mapping_file_path,
                    )
                else:
                    logger.warning(
                        "No triples generated from mapping %s.", mapping_file_path
                    )

                return graph

        except Exception as exc:
            logger.error(
                "Error applying RML mapping %s: %s",
                mapping_file_path,
                exc,
                exc_info=True,
            )
            return None

    def _normalize_schema_uris(self, payload: Any):
        if isinstance(payload, dict):
            normalized = {}
            for key, value in payload.items():
                if key == "@context":
                    continue
                next_key = (
                    self._normalize_schema_uris(key) if isinstance(key, str) else key
                )
                normalized[next_key] = self._normalize_schema_uris(value)
            return normalized
        if isinstance(payload, list):
            return [self._normalize_schema_uris(item) for item in payload]
        if isinstance(payload, str):
            return payload.replace("https://schema.org", "http://schema.org")
        return payload
