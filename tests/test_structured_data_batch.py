from __future__ import annotations

import json
from pathlib import Path

import pytest

from wordlift_sdk.structured_data.batch import BatchGenerator


class _Rendered:
    def __init__(self, xhtml: str, status_code: int | None = 200):
        self.xhtml = xhtml
        self.status_code = status_code


def _make_generator(
    tmp_path: Path, output_format: str = "jsonld", concurrency: str = "1"
) -> BatchGenerator:
    return BatchGenerator(
        output_dir=tmp_path / "out",
        output_format=output_format,
        concurrency=concurrency,
        headed=False,
        timeout_ms=100,
        wait_until="load",
        max_xhtml_chars=1000,
        max_text_node_chars=100,
        dataset_uri="https://data.example.org",
        verbose=False,
    )


def test_batch_generate_errors_for_invalid_inputs(tmp_path: Path):
    gen = _make_generator(tmp_path)
    with pytest.raises(RuntimeError, match="No URLs"):
        gen.generate([], "mappings: {}", lambda *_: None)

    bad = _make_generator(tmp_path, concurrency="abc")
    with pytest.raises(RuntimeError, match="integer or 'auto'"):
        bad.generate(["https://example.org"], "mappings: {}", lambda *_: None)

    bad2 = _make_generator(tmp_path, concurrency="0")
    with pytest.raises(RuntimeError, match="greater than 0"):
        bad2.generate(["https://example.org"], "mappings: {}", lambda *_: None)


def test_batch_generate_success_jsonld(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    gen = _make_generator(tmp_path, output_format="jsonld", concurrency="1")

    monkeypatch.setattr(
        "wordlift_sdk.structured_data.batch.render_html",
        lambda options: _Rendered("<html/>", 200),
    )
    monkeypatch.setattr(
        "wordlift_sdk.structured_data.batch.clean_xhtml",
        lambda xhtml, options: "<clean/>",
    )

    gen._yarrrml.build_output_basename = lambda url: "page-1"
    gen._yarrrml.ensure_no_blank_nodes = lambda graph: None
    gen._materializer.normalize = lambda yarrrml, url, xhtml_path: (yarrrml, [])
    gen._materializer.materialize = lambda normalized, xhtml_path, workdir, url=None: {
        "@graph": []
    }
    gen._materializer.postprocess = lambda raw, mappings, xhtml, dataset_uri, url: {
        "@graph": [
            {
                "@id": "https://example.org/page-1",
                "@type": ["https://schema.org/WebPage"],
            }
        ]
    }

    summary = gen.generate(
        ["https://example.org/page-1"], "mappings: {}", lambda *_: None
    )
    assert summary["success"] == 1
    assert summary["failed"] == 0

    out = tmp_path / "out" / "page-1.jsonld"
    payload = json.loads(out.read_text())
    assert payload["@graph"][0]["@id"] == "https://example.org/page-1"


def test_batch_generate_success_ttl_and_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    gen = _make_generator(tmp_path, output_format="ttl", concurrency="1")

    def _render(options):
        if "bad" in options.url:
            raise RuntimeError("render-failed")
        return _Rendered("<html/>", 429)

    monkeypatch.setattr("wordlift_sdk.structured_data.batch.render_html", _render)
    monkeypatch.setattr(
        "wordlift_sdk.structured_data.batch.clean_xhtml",
        lambda xhtml, options: "<clean/>",
    )
    monkeypatch.setattr(
        "wordlift_sdk.structured_data.batch.serialize_graph",
        lambda graph, output_format: "<s> <p> <o> .",
    )

    gen._yarrrml.build_output_basename = lambda url: "good" if "good" in url else "bad"
    gen._yarrrml.ensure_no_blank_nodes = lambda graph: None
    gen._materializer.normalize = lambda yarrrml, url, xhtml_path: (yarrrml, [])
    gen._materializer.materialize = lambda normalized, xhtml_path, workdir, url=None: {
        "@graph": []
    }
    gen._materializer.postprocess = lambda raw, mappings, xhtml, dataset_uri, url: {
        "@graph": [
            {"@id": "https://example.org/x", "@type": ["https://schema.org/Thing"]}
        ]
    }

    summary = gen.generate(
        ["https://example.org/good", "https://example.org/bad"],
        "mappings: {}",
        lambda *_: None,
    )

    assert summary["success"] == 1
    assert summary["failed"] == 1
    assert summary["errors"][0]["url"].endswith("/bad")
    assert (tmp_path / "out" / "good.ttl").read_text() == "<s> <p> <o> ."


def test_batch_status_bucket_and_auto_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    gen = _make_generator(tmp_path, output_format="jsonld", concurrency="auto")

    assert gen._status_bucket(None) == "error"
    assert gen._status_bucket(429) == "throttle"
    assert gen._status_bucket(503) == "server_error"
    assert gen._status_bucket(204) == "ok"
    assert gen._status_bucket(404) == "client_error"

    monkeypatch.setattr(
        "wordlift_sdk.structured_data.batch.render_html",
        lambda options: _Rendered("<html/>", 200),
    )
    monkeypatch.setattr(
        "wordlift_sdk.structured_data.batch.clean_xhtml",
        lambda xhtml, options: "<clean/>",
    )
    gen._yarrrml.build_output_basename = lambda url: url.rsplit("/", 1)[-1]
    gen._yarrrml.ensure_no_blank_nodes = lambda graph: None
    gen._materializer.normalize = lambda yarrrml, url, xhtml_path: (yarrrml, [])
    gen._materializer.materialize = lambda normalized, xhtml_path, workdir, url=None: {
        "@graph": []
    }
    gen._materializer.postprocess = lambda raw, mappings, xhtml, dataset_uri, url: {
        "@graph": [{"@id": f"{url}", "@type": ["https://schema.org/Thing"]}]
    }

    summary = gen.generate(
        ["https://example.org/a", "https://example.org/b"],
        "mappings: {}",
        lambda *_: None,
    )
    assert summary["total"] == 2
