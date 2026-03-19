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
from typing import Any

from rdflib import Graph

from .types import (
    Closeable,
    GraphPostprocessor,
    LoadedPostprocessor,
    PostprocessorContext,
    PostprocessorRuntime,
    PostprocessorSpec,
    PersistentWorkerJobError,
    PersistentWorkerTransportError,
    _SubprocessRunner,
)

logger = logging.getLogger(__name__)


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
            "wordlift_sdk.kg_build.postprocessors.persistent",
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


def _run_subprocess(
    spec: PostprocessorSpec,
    root_dir: Path,
    graph: Graph,
    payload: dict[str, Any],
    runner: _SubprocessRunner,
) -> Graph | None:
    """Shared scaffolding for subprocess-based postprocessors.

    Handles temp-dir lifecycle, graph serialization, output verification,
    and debug-copy on failure. *runner* is called with the prepared paths
    and is responsible only for the actual subprocess execution step.
    """
    from .graph_io import _redact_debug_context, _read_graph_nquads, _write_graph_nquads

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

        runner(
            input_graph_path=input_graph_path,
            output_graph_path=output_graph_path,
            context_path=context_path,
            context_payload=payload,
        )

        if not output_graph_path.exists():
            failed = True
            raise RuntimeError(
                f"Postprocessor did not produce output graph: {spec.class_path}"
            )

        return _read_graph_nquads(output_graph_path)
    except Exception:
        failed = True
        raise
    finally:
        if failed and spec.keep_temp_on_error:
            debug_dir = root_dir / "output" / "postprocessor_debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            target = debug_dir / (spec.class_path.replace(":", "_").replace(".", "_"))
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(temp_dir_path, target)
            _redact_debug_context(target / "context.json")
        if temp_dir_path.exists():
            shutil.rmtree(temp_dir_path, ignore_errors=True)


@dataclass(frozen=True)
class OneshotSubprocessPostprocessor:
    spec: PostprocessorSpec
    root_dir: Path

    def process_graph(
        self, graph: Graph, context: PostprocessorContext
    ) -> Graph | None:
        from .graph_io import _build_runner_payload
        return _run_subprocess(
            self.spec, self.root_dir, graph, _build_runner_payload(context), self._run
        )

    def _run(
        self,
        *,
        input_graph_path: Path,
        output_graph_path: Path,
        context_path: Path,
        **_: Any,
    ) -> None:
        cmd = [
            self.spec.python,
            "-m",
            "wordlift_sdk.kg_build.postprocessors.oneshot",
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


@dataclass
class PersistentSubprocessPostprocessor:
    spec: PostprocessorSpec
    root_dir: Path
    _client: PersistentPostprocessorClient | None = field(
        init=False,
        default=None,
        repr=False,
    )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def process_graph(
        self, graph: Graph, context: PostprocessorContext
    ) -> Graph | None:
        from .graph_io import _build_runner_payload
        return _run_subprocess(
            self.spec, self.root_dir, graph, _build_runner_payload(context), self._run
        )

    def _run(
        self,
        *,
        input_graph_path: Path,
        output_graph_path: Path,
        context_payload: dict[str, Any],
        **_: Any,
    ) -> None:
        if self._client is None:
            self._client = PersistentPostprocessorClient(
                spec=self.spec,
                root_dir=self.root_dir,
            )
        self._client.process_graph(
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


def _build_handler(
    spec: PostprocessorSpec, root_dir: Path, runtime: PostprocessorRuntime
) -> GraphPostprocessor:
    if runtime == PostprocessorRuntime.INPROCESS:
        return InProcessPostprocessor(class_path=spec.class_path)
    if runtime == PostprocessorRuntime.PERSISTENT:
        return PersistentSubprocessPostprocessor(spec=spec, root_dir=root_dir)
    return OneshotSubprocessPostprocessor(spec=spec, root_dir=root_dir)


def _normalize_runtime(value: str | None) -> PostprocessorRuntime:
    raw = (value or PostprocessorRuntime.ONESHOT.value).strip().lower()
    try:
        return PostprocessorRuntime(raw)
    except ValueError:
        raise ValueError(
            "POSTPROCESSOR_RUNTIME must be one of: oneshot, persistent, inprocess."
        )
