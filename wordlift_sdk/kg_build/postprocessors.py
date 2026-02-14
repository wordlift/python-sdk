from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from rdflib import Dataset, Graph

logger = logging.getLogger(__name__)

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


@dataclass(frozen=True)
class PostprocessorContext:
    profile_name: str
    url: str
    account: Any
    exports: dict[str, Any]
    response: Any
    settings: dict[str, Any]
    ids: Any | None = None


@runtime_checkable
class GraphPostprocessor(Protocol):
    def process_graph(
        self, graph: Graph, context: PostprocessorContext
    ) -> Graph | None: ...


@dataclass(frozen=True)
class LoadedPostprocessor:
    name: str
    handler: GraphPostprocessor

    def run(self, graph: Graph, context: PostprocessorContext) -> Graph:
        result = self.handler.process_graph(graph, context)
        return graph if result is None else result


@dataclass(frozen=True)
class PostprocessorSpec:
    class_path: str
    python: str
    timeout_seconds: int
    enabled: bool
    keep_temp_on_error: bool


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise TypeError("Expected boolean value.")


def _as_str(value: Any, default: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str) or not value.strip():
        raise TypeError("Expected non-empty string value.")
    return value


def _as_positive_int(value: Any, default: int) -> int:
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
        spec = PostprocessorSpec(
            class_path=class_path.strip(),
            python=_as_str(row.get("python"), default_python),
            timeout_seconds=_as_positive_int(
                row.get("timeout_seconds"), default_timeout
            ),
            enabled=_as_bool(row.get("enabled"), default_enabled),
            keep_temp_on_error=_as_bool(
                row.get("keep_temp_on_error"), default_keep_temp
            ),
        )
        specs.append(spec)
    return specs


def _build_runner_payload(context: PostprocessorContext) -> dict[str, Any]:
    account = getattr(context, "account", None)
    dataset_uri = str(getattr(account, "dataset_uri", "")).rstrip("/")
    country_code = str(getattr(account, "country_code", "")).strip().lower()
    response = getattr(context, "response", None)
    web_page = getattr(response, "web_page", None) if response else None
    return {
        "profile_name": context.profile_name,
        "url": context.url,
        "dataset_uri": dataset_uri,
        "country_code": country_code,
        "exports": context.exports,
        "settings": context.settings,
        "response": {
            "id": getattr(response, "id", None),
            "web_page": {
                "url": getattr(web_page, "url", None),
                "html": getattr(web_page, "html", None),
            },
        },
    }


@dataclass(frozen=True)
class SubprocessPostprocessor:
    spec: PostprocessorSpec
    root_dir: Path

    def process_graph(
        self, graph: Graph, context: PostprocessorContext
    ) -> Graph | None:
        payload = _build_runner_payload(context)
        temp_dir_path = Path(tempfile.mkdtemp(prefix="worai_pp_"))
        failed = False
        try:
            input_graph_path = temp_dir_path / "input_graph.nq"
            output_graph_path = temp_dir_path / "output_graph.nq"
            context_path = temp_dir_path / "context.json"

            _write_graph_nquads(graph, input_graph_path)
            context_path.write_text(
                json.dumps(payload, ensure_ascii=True, default=str),
                encoding="utf-8",
            )

            cmd = [
                self.spec.python,
                "-m",
                "wordlift_sdk.kg_build.postprocessor_runner",
                "--class",
                self.spec.class_path,
                "--input-graph",
                str(input_graph_path),
                "--output-graph",
                str(output_graph_path),
                "--context",
                str(context_path),
            ]
            completed = subprocess.run(
                cmd,
                text=True,
                capture_output=True,
                cwd=str(self.root_dir),
                timeout=self.spec.timeout_seconds,
                check=False,
            )
            if completed.returncode != 0:
                failed = True
                stderr = (completed.stderr or "").strip()
                raise RuntimeError(
                    f"Postprocessor failed: {self.spec.class_path} "
                    f"(exit={completed.returncode})" + (f"\n{stderr}" if stderr else "")
                )

            if not output_graph_path.exists():
                failed = True
                raise RuntimeError(
                    "Postprocessor did not produce output graph: "
                    f"{self.spec.class_path}"
                )

            return _read_graph_nquads(output_graph_path)
        except Exception:
            failed = True
            raise
        finally:
            if failed and self.spec.keep_temp_on_error:
                debug_dir = self.root_dir / "output" / "postprocessor_debug"
                debug_dir.mkdir(parents=True, exist_ok=True)
                target = debug_dir / (
                    self.spec.class_path.replace(":", "_").replace(".", "_")
                )
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(temp_dir_path, target)
            if temp_dir_path.exists():
                shutil.rmtree(temp_dir_path, ignore_errors=True)


def load_postprocessors_for_profile(
    *, root_dir: Path, profile_name: str
) -> list[LoadedPostprocessor]:
    base_manifest = root_dir / "profiles" / "_base" / "postprocessors.toml"
    profile_manifest = root_dir / "profiles" / profile_name / "postprocessors.toml"

    specs: list[PostprocessorSpec] = []
    specs.extend(_load_manifest_specs(base_manifest))
    specs.extend(_load_manifest_specs(profile_manifest))

    loaded: list[LoadedPostprocessor] = []
    for spec in specs:
        if not spec.enabled:
            continue
        loaded.append(
            LoadedPostprocessor(
                name=spec.class_path,
                handler=SubprocessPostprocessor(spec=spec, root_dir=root_dir),
            )
        )

    logger.info(
        "Loaded %s postprocessors for profile '%s' from manifests: %s, %s",
        len(loaded),
        profile_name,
        base_manifest,
        profile_manifest,
    )
    return loaded


def load_postprocessors(
    manifest_path: Path, *, root_dir: Path
) -> list[LoadedPostprocessor]:
    specs = _load_manifest_specs(manifest_path)
    loaded: list[LoadedPostprocessor] = []
    for spec in specs:
        if not spec.enabled:
            continue
        loaded.append(
            LoadedPostprocessor(
                name=spec.class_path,
                handler=SubprocessPostprocessor(spec=spec, root_dir=root_dir),
            )
        )
    return loaded


def _write_graph_nquads(graph: Graph, path: Path) -> None:
    dataset = Dataset()
    for triple in graph:
        dataset.add(triple)
    dataset.serialize(destination=path, format="nquads")


def _read_graph_nquads(path: Path) -> Graph:
    dataset = Dataset()
    dataset.parse(path, format="nquads")
    graph = Graph()
    for triple in dataset.triples((None, None, None)):
        graph.add(triple)
    return graph
