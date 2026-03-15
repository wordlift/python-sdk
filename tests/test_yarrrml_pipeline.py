from __future__ import annotations

import pytest

import wordlift_sdk.structured_data.yarrrml_pipeline as yarrrml_pipeline_module
from wordlift_sdk.structured_data.yarrrml_pipeline import YarrrmlPipeline


def test_yarrrml_pipeline_reusable_and_basename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline = YarrrmlPipeline()

    monkeypatch.setattr(
        yarrrml_pipeline_module,
        "make_reusable_yarrrml",
        lambda yarrrml, url: f"# {url}\n{yarrrml}",
    )
    monkeypatch.setattr(
        yarrrml_pipeline_module, "build_output_basename", lambda url: "example"
    )

    assert pipeline.make_reusable_yarrrml(
        "mappings: []", "https://example.com"
    ).startswith("# https://example.com")
    assert pipeline.build_output_basename("https://example.com") == "example"
