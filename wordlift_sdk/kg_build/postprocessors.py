from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import logging
import select
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from rdflib import Dataset, Graph

logger = logging.getLogger(__name__)

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

_RUNTIME_ONESHOT = "oneshot"
_RUNTIME_PERSISTENT = "persistent"
_RUNTIME_INPROCESS = "inprocess"


@dataclass(frozen=True)
class PostprocessorContext:
    profile_name: str
    profile: dict[str, Any]
    url: str
    account: Any
    account_key: str | None
    exports: dict[str, Any]
    response: Any
    existing_web_page_id: str | None
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


class PersistentWorkerTransportError(RuntimeError):
    pass


class PersistentWorkerJobError(RuntimeError):
    pass


class PersistentPostprocessorClient:
    def __init__(self, *, spec: PostprocessorSpec, root_dir: Path) -> None:
        self._spec = spec
        self._root_dir = root_dir
        self._process: subprocess.Popen[str] | None = None
        self._next_job_id = 0

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return

        try:
            if process.poll() is None and process.stdin is not None:
                process.stdin.write(json.dumps({"op": "shutdown"}) + "\n")
                process.stdin.flush()
        except Exception:
            pass

        self._terminate(process)

    def process_graph(
        self,
        *,
        input_graph_path: Path,
        output_graph_path: Path,
        context_payload: dict[str, Any],
    ) -> None:
        for attempt in range(2):
            try:
                self._process_graph_once(
                    input_graph_path=input_graph_path,
                    output_graph_path=output_graph_path,
                    context_payload=context_payload,
                )
                return
            except PersistentWorkerTransportError:
                self.close()
                if attempt == 1:
                    raise

    def _process_graph_once(
        self,
        *,
        input_graph_path: Path,
        output_graph_path: Path,
        context_payload: dict[str, Any],
    ) -> None:
        process = self._ensure_started()
        self._next_job_id += 1
        job_id = self._next_job_id

        payload = {
            "op": "process",
            "id": job_id,
            "input_graph": str(input_graph_path),
            "output_graph": str(output_graph_path),
            "context": context_payload,
        }

        try:
            assert process.stdin is not None
            process.stdin.write(
                json.dumps(payload, ensure_ascii=True, default=str) + "\n"
            )
            process.stdin.flush()
        except Exception as exc:
            raise PersistentWorkerTransportError(
                f"Postprocessor worker stdin failed: {self._spec.class_path}"
            ) from exc

        message = self._read_message(
            process, timeout_seconds=self._spec.timeout_seconds
        )
        if message.get("id") != job_id:
            raise PersistentWorkerTransportError(
                f"Postprocessor worker returned invalid response id for {self._spec.class_path}."
            )
        if message.get("ok") is True:
            return

        error = str(message.get("error") or "unknown worker error")
        raise PersistentWorkerJobError(
            f"Postprocessor failed: {self._spec.class_path}\n{error}".strip()
        )

    def _ensure_started(self) -> subprocess.Popen[str]:
        process = self._process
        if process is not None and process.poll() is None:
            return process

        cmd = [
            self._spec.python,
            "-m",
            "wordlift_sdk.kg_build.postprocessor_worker",
            "--class",
            self._spec.class_path,
        ]
        process = subprocess.Popen(
            cmd,
            text=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self._root_dir),
            bufsize=1,
        )

        try:
            ready = self._read_message(
                process, timeout_seconds=min(self._spec.timeout_seconds, 60)
            )
        except Exception:
            self._terminate(process)
            raise

        if ready.get("op") != "ready" or ready.get("ok") is not True:
            stderr = self._read_stderr(process)
            self._terminate(process)
            raise PersistentWorkerTransportError(
                f"Postprocessor worker failed to start: {self._spec.class_path}"
                + (f"\n{stderr}" if stderr else "")
            )

        self._process = process
        return process

    def _read_message(
        self,
        process: subprocess.Popen[str],
        *,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        if process.stdout is None:
            raise PersistentWorkerTransportError("Worker stdout is unavailable.")

        ready, _, _ = select.select([process.stdout], [], [], timeout_seconds)
        if not ready:
            self._terminate(process)
            cmd = (
                process.args if isinstance(process.args, list) else [str(process.args)]
            )
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout_seconds)

        line = process.stdout.readline()
        if not line:
            stderr = self._read_stderr(process)
            self._terminate(process)
            raise PersistentWorkerTransportError(
                f"Postprocessor worker exited unexpectedly: {self._spec.class_path}"
                + (f"\n{stderr}" if stderr else "")
            )

        try:
            return json.loads(line)
        except json.JSONDecodeError as exc:
            raise PersistentWorkerTransportError(
                "Postprocessor worker returned invalid JSON response."
            ) from exc

    def _read_stderr(self, process: subprocess.Popen[str]) -> str:
        if process.stderr is None:
            return ""
        try:
            return (process.stderr.read() or "").strip()
        except Exception:
            return ""

    def _terminate(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass


@dataclass
class SubprocessPostprocessor:
    spec: PostprocessorSpec
    root_dir: Path
    runtime: str = _RUNTIME_ONESHOT
    _persistent_client: PersistentPostprocessorClient | None = field(
        init=False,
        default=None,
        repr=False,
    )

    def close(self) -> None:
        if self._persistent_client is not None:
            self._persistent_client.close()
            self._persistent_client = None

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

            if self.runtime == _RUNTIME_PERSISTENT:
                self._run_persistent(
                    input_graph_path=input_graph_path,
                    output_graph_path=output_graph_path,
                    context_payload=payload,
                )
            else:
                self._run_oneshot(
                    input_graph_path=input_graph_path,
                    output_graph_path=output_graph_path,
                    context_path=context_path,
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
                _redact_debug_context(target / "context.json")
            if temp_dir_path.exists():
                shutil.rmtree(temp_dir_path, ignore_errors=True)

    def _run_oneshot(
        self,
        *,
        input_graph_path: Path,
        output_graph_path: Path,
        context_path: Path,
    ) -> None:
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
            stderr = (completed.stderr or "").strip()
            raise RuntimeError(
                f"Postprocessor failed: {self.spec.class_path} "
                f"(exit={completed.returncode})" + (f"\n{stderr}" if stderr else "")
            )

    def _run_persistent(
        self,
        *,
        input_graph_path: Path,
        output_graph_path: Path,
        context_payload: dict[str, Any],
    ) -> None:
        if self._persistent_client is None:
            self._persistent_client = PersistentPostprocessorClient(
                spec=self.spec,
                root_dir=self.root_dir,
            )
        self._persistent_client.process_graph(
            input_graph_path=input_graph_path,
            output_graph_path=output_graph_path,
            context_payload=context_payload,
        )


@dataclass(frozen=True)
class InProcessPostprocessor:
    class_path: str

    def process_graph(
        self, graph: Graph, context: PostprocessorContext
    ) -> Graph | None:
        module_name, class_name = self.class_path.split(":", 1)
        module = importlib.import_module(module_name)
        klass = getattr(module, class_name)
        processor = klass()
        result = processor.process_graph(graph, context)
        if inspect.isawaitable(result):
            result = asyncio.run(result)
        return result


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


def _build_handler(
    spec: PostprocessorSpec, root_dir: Path, runtime: str
) -> GraphPostprocessor:
    if runtime == _RUNTIME_INPROCESS:
        return InProcessPostprocessor(class_path=spec.class_path)
    return SubprocessPostprocessor(spec=spec, root_dir=root_dir, runtime=runtime)


def _normalize_runtime(value: str | None) -> str:
    runtime = (value or _RUNTIME_ONESHOT).strip().lower()
    if runtime not in {_RUNTIME_ONESHOT, _RUNTIME_PERSISTENT, _RUNTIME_INPROCESS}:
        raise ValueError(
            "POSTPROCESSOR_RUNTIME must be one of: oneshot, persistent, inprocess."
        )
    return runtime


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
    account_key = (
        str(context.account_key).strip()
        if getattr(context, "account_key", None) is not None
        else ""
    )
    profile = dict(getattr(context, "profile", {}) or {})
    if "settings" not in profile or not isinstance(profile.get("settings"), dict):
        profile["settings"] = {}
    profile_settings = dict(profile.get("settings", {}) or {})
    profile_settings.setdefault("api_url", "https://api.wordlift.io")
    profile["settings"] = profile_settings
    response = getattr(context, "response", None)
    web_page = getattr(response, "web_page", None) if response else None
    return {
        "profile_name": context.profile_name,
        "profile": profile,
        "url": context.url,
        "dataset_uri": dataset_uri,
        "country_code": country_code,
        "account_key": account_key or None,
        "exports": context.exports,
        "existing_web_page_id": context.existing_web_page_id,
        "response": {
            "id": getattr(response, "id", None) or context.existing_web_page_id,
            "web_page": {
                "url": getattr(web_page, "url", None),
                "html": getattr(web_page, "html", None),
            },
        },
    }


def _load_from_specs(
    specs: list[PostprocessorSpec],
    root_dir: Path,
    runtime: str,
) -> list[LoadedPostprocessor]:
    return [
        LoadedPostprocessor(
            name=spec.class_path,
            handler=_build_handler(spec, root_dir, runtime),
        )
        for spec in specs
        if spec.enabled
    ]


def load_postprocessors_for_profile(
    *,
    root_dir: Path,
    profile_name: str,
    runtime: str | None = None,
) -> list[LoadedPostprocessor]:
    base_manifest = root_dir / "profiles" / "_base" / "postprocessors.toml"
    profile_manifest = root_dir / "profiles" / profile_name / "postprocessors.toml"

    if profile_manifest.exists():
        selected_manifest: Path | None = profile_manifest
    elif base_manifest.exists():
        selected_manifest = base_manifest
    else:
        selected_manifest = None

    logger.debug(
        "Postprocessor manifest precedence for profile '%s': profile=%s base=%s chosen=%s",
        profile_name,
        profile_manifest,
        base_manifest,
        selected_manifest or "none",
    )
    return load_postprocessors(selected_manifest, root_dir=root_dir, runtime=runtime)


def load_postprocessors(
    manifest_path: Path | None,
    *,
    root_dir: Path,
    runtime: str | None = None,
) -> list[LoadedPostprocessor]:
    specs = _load_manifest_specs(manifest_path) if manifest_path else []
    resolved_runtime = _normalize_runtime(runtime)
    loaded = _load_from_specs(specs, root_dir, resolved_runtime)
    logger.info(
        "Loaded %s postprocessors from manifest: %s (runtime=%s)",
        len(loaded),
        manifest_path or "none",
        resolved_runtime,
    )
    return loaded


def close_loaded_postprocessors(postprocessors: list[LoadedPostprocessor]) -> None:
    for processor in postprocessors:
        close = getattr(processor.handler, "close", None)
        if callable(close):
            close()


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


def _redact_debug_context(path: Path) -> None:
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(payload, dict):
        return
    if payload.get("account_key"):
        payload["account_key"] = "***REDACTED***"
    profile = payload.get("profile")
    if isinstance(profile, dict) and profile.get("api_key"):
        profile["api_key"] = "***REDACTED***"
    settings = (
        profile.get("settings")
        if isinstance(profile, dict) and isinstance(profile.get("settings"), dict)
        else None
    )
    if settings and settings.get("api_key"):
        settings["api_key"] = "***REDACTED***"
    if settings and settings.get("wordlift_key"):
        settings["wordlift_key"] = "***REDACTED***"
    if settings and settings.get("WORDLIFT_KEY"):
        settings["WORDLIFT_KEY"] = "***REDACTED***"
    if settings and settings.get("WORDLIFT_API_KEY"):
        settings["WORDLIFT_API_KEY"] = "***REDACTED***"
    payload["profile"] = profile
    path.write_text(
        json.dumps(payload, ensure_ascii=True, default=str),
        encoding="utf-8",
    )
