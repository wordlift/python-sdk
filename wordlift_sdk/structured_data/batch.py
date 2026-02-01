"""Batch generation for structured data using YARRRML mappings."""

from __future__ import annotations

import json
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from rdflib import Graph

from wordlift_sdk.structured_data.yarrrml_pipeline import YarrrmlPipeline
from wordlift_sdk.render import CleanupOptions, RenderOptions, clean_xhtml, render_html

from .io import normalize_output_format, serialize_graph, write_output
from .materialization import MaterializationPipeline


class BatchGenerator:
    """Processes a list of URLs to generate structured data outputs."""

    def __init__(
        self,
        output_dir: Path,
        output_format: str,
        concurrency: str,
        headed: bool,
        timeout_ms: int,
        wait_until: str,
        max_xhtml_chars: int,
        max_text_node_chars: int,
        dataset_uri: str,
        verbose: bool,
    ) -> None:
        self._output_dir = output_dir
        self._output_format = output_format
        self._concurrency = concurrency
        self._dataset_uri = dataset_uri
        self._verbose = verbose
        self._headed = headed
        self._timeout_ms = timeout_ms
        self._wait_until = wait_until
        self._max_xhtml_chars = max_xhtml_chars
        self._max_text_node_chars = max_text_node_chars
        self._yarrrml = YarrrmlPipeline()
        self._materializer = MaterializationPipeline(self._yarrrml)

    def generate(
        self, urls: list[str], yarrrml: str, log: Callable[[str], None]
    ) -> dict[str, object]:
        if not urls:
            raise RuntimeError("No URLs provided for generation.")

        _, extension = normalize_output_format(self._output_format)
        self._output_dir.mkdir(parents=True, exist_ok=True)

        auto_concurrency = self._concurrency.strip().lower() == "auto"
        if auto_concurrency:
            min_workers = 2
            max_workers = 12
            current_workers = min(max_workers, max(min_workers, 4))
        else:
            try:
                current_workers = int(self._concurrency)
            except ValueError as exc:
                raise RuntimeError("Concurrency must be an integer or 'auto'.") from exc
            if current_workers <= 0:
                raise RuntimeError("Concurrency must be greater than 0.")
            min_workers = max_workers = current_workers

        results: list[dict[str, object]] = []
        errors: list[dict[str, str]] = []

        with tempfile.TemporaryDirectory(prefix="structured-data-generate-") as tmp_dir:
            tmp_root = Path(tmp_dir)
            index = 0
            total = len(urls)
            if self._verbose:
                log(f"Processing {total} URLs...")
            from tqdm import tqdm

            progress = tqdm(total=total, disable=not self._verbose)

            def _process_url(url: str) -> dict[str, object]:
                status_code = None
                try:
                    step_start = time.perf_counter()
                    log(f"Start: {url}")
                    render_options = RenderOptions(
                        url=url,
                        headless=not self._headed,
                        timeout_ms=self._timeout_ms,
                        wait_until=self._wait_until,
                    )
                    rendered = render_html(render_options)
                    log(f"Rendered: {url} in {time.perf_counter() - step_start:.2f}s")
                    status_code = getattr(rendered, "status_code", None)
                    step_start = time.perf_counter()
                    cleanup_options = CleanupOptions(
                        max_xhtml_chars=self._max_xhtml_chars,
                        max_text_node_chars=self._max_text_node_chars,
                    )
                    cleaned_xhtml = clean_xhtml(rendered.xhtml, cleanup_options)
                    log(
                        f"Cleaned XHTML: {url} in {time.perf_counter() - step_start:.2f}s"
                    )
                    basename = self._yarrrml.build_output_basename(url)
                    xhtml_path = tmp_root / f"{basename}.xhtml"
                    xhtml_path.write_text(cleaned_xhtml)
                    workdir = tmp_root / f"work-{basename}"
                    step_start = time.perf_counter()
                    normalized_yarrrml, mappings = self._materializer.normalize(
                        yarrrml,
                        url,
                        xhtml_path,
                        target_type=None,
                    )
                    log(
                        f"Normalized YARRRML: {url} in {time.perf_counter() - step_start:.2f}s"
                    )
                    step_start = time.perf_counter()
                    jsonld_raw = self._materializer.materialize(
                        normalized_yarrrml, xhtml_path, workdir, url=url
                    )
                    log(
                        f"Materialized JSON-LD: {url} in {time.perf_counter() - step_start:.2f}s"
                    )
                    step_start = time.perf_counter()
                    jsonld = self._materializer.postprocess(
                        jsonld_raw,
                        mappings,
                        cleaned_xhtml,
                        self._dataset_uri,
                        url,
                        target_type=None,
                    )
                    log(
                        f"Postprocessed JSON-LD: {url} in {time.perf_counter() - step_start:.2f}s"
                    )
                    step_start = time.perf_counter()
                    graph = Graph()
                    graph.parse(data=json.dumps(jsonld), format="json-ld")
                    self._yarrrml.ensure_no_blank_nodes(graph)
                    output_path = self._output_dir / f"{basename}.{extension}"
                    if self._output_format.lower() in {"jsonld", "json-ld"}:
                        write_output(output_path, json.dumps(jsonld, indent=2))
                    else:
                        serialized = serialize_graph(graph, self._output_format)
                        write_output(output_path, serialized)
                    log(
                        f"Wrote output: {url} in {time.perf_counter() - step_start:.2f}s"
                    )
                    return {
                        "ok": True,
                        "url": url,
                        "status_code": status_code,
                        "output": str(output_path),
                    }
                except Exception as exc:
                    log(f"Failed: {url} with {exc}")
                    return {
                        "ok": False,
                        "url": url,
                        "status_code": status_code,
                        "error": str(exc),
                    }

            while index < total:
                batch = urls[index : index + current_workers]
                if not batch:
                    break
                batch_results: list[dict[str, object]] = []
                with ThreadPoolExecutor(max_workers=current_workers) as executor:
                    futures = {executor.submit(_process_url, url): url for url in batch}
                    for future in as_completed(futures):
                        result = future.result()
                        batch_results.append(result)
                        progress.update(1)
                        if not result.get("ok"):
                            errors.append(
                                {
                                    "url": str(result.get("url")),
                                    "error": str(result.get("error")),
                                }
                            )
                results.extend(batch_results)

                if auto_concurrency:
                    buckets = {
                        self._status_bucket(item.get("status_code"))
                        for item in batch_results
                    }
                    if buckets & {"throttle", "server_error", "error"}:
                        current_workers = max(min_workers, current_workers - 1)
                    elif buckets == {"ok"}:
                        current_workers = min(max_workers, current_workers + 1)
                index += len(batch)
            progress.close()

        return {
            "format": self._output_format,
            "output_dir": str(self._output_dir),
            "total": len(urls),
            "success": sum(1 for item in results if item.get("ok")),
            "failed": sum(1 for item in results if not item.get("ok")),
            "errors": errors,
        }

    def _status_bucket(self, status_code: int | None) -> str:
        if status_code is None:
            return "error"
        if status_code == 429:
            return "throttle"
        if 500 <= status_code < 600:
            return "server_error"
        if 200 <= status_code < 400:
            return "ok"
        return "client_error"
