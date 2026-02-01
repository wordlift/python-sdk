"""Materialization pipeline for YARRRML -> JSON-LD."""

from __future__ import annotations

from pathlib import Path

from wordlift_sdk.structured_data.yarrrml_pipeline import YarrrmlPipeline


class MaterializationPipeline:
    """Normalizes mappings, materializes JSON-LD, and post-processes output."""

    def __init__(self, pipeline: YarrrmlPipeline | None = None) -> None:
        self._pipeline = pipeline or YarrrmlPipeline()

    def normalize(
        self, yarrrml: str, url: str, xhtml_path: Path, target_type: str | None
    ) -> tuple[str, list[dict]]:
        return self._pipeline.normalize_mappings(
            yarrrml, url, xhtml_path, target_type=target_type
        )

    def materialize(
        self, normalized_yarrrml: str, xhtml_path: Path, workdir: Path, url: str
    ) -> dict:
        return self._pipeline.materialize_jsonld(
            normalized_yarrrml, xhtml_path, workdir, url=url
        )

    def postprocess(
        self,
        jsonld_raw: dict,
        mappings: list[dict],
        cleaned_xhtml: str,
        dataset_uri: str,
        url: str,
        target_type: str | None,
    ) -> dict:
        return self._pipeline.postprocess_jsonld(
            jsonld_raw,
            mappings,
            cleaned_xhtml,
            dataset_uri,
            url,
            target_type=target_type,
        )

    def run(
        self,
        yarrrml: str,
        url: str,
        cleaned_xhtml: str,
        dataset_uri: str,
        xhtml_path: Path,
        workdir: Path,
        target_type: str | None,
    ) -> tuple[dict, list[dict]]:
        normalized_yarrrml, mappings = self.normalize(
            yarrrml, url, xhtml_path, target_type=target_type
        )
        jsonld_raw = self.materialize(normalized_yarrrml, xhtml_path, workdir, url=url)
        jsonld = self.postprocess(
            jsonld_raw,
            mappings,
            cleaned_xhtml,
            dataset_uri,
            url,
            target_type=target_type,
        )
        return jsonld, mappings
