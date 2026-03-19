from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from rdflib import Graph


class PostprocessorRuntime(str, Enum):
    ONESHOT = "oneshot"
    PERSISTENT = "persistent"
    INPROCESS = "inprocess"


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
    existing_import_hash: str | None = None
    import_hash_mode: str = "on"
    ids: Any | None = None


@dataclass(frozen=True)
class PostprocessorSpec:
    class_path: str
    python: str
    timeout_seconds: int
    enabled: bool
    keep_temp_on_error: bool


class _SubprocessRunner(Protocol):
    def __call__(
        self,
        *,
        input_graph_path: Path,
        output_graph_path: Path,
        context_path: Path,
        context_payload: dict[str, Any],
    ) -> None: ...


@runtime_checkable
class Closeable(Protocol):
    def close(self) -> None: ...


@runtime_checkable
class GraphPostprocessor(Protocol):
    def process_graph(
        self, graph: Graph, context: PostprocessorContext
    ) -> Graph | None: ...


@dataclass(frozen=True)
class PostprocessorResult:
    graph: Graph
    queue_wait_ms: int
    postprocessors_ms: int


@dataclass(frozen=True)
class LoadedPostprocessor:
    name: str
    handler: GraphPostprocessor

    def run(self, graph: Graph, context: PostprocessorContext) -> Graph:
        result = self.handler.process_graph(graph, context)
        return graph if result is None else result


class PersistentWorkerTransportError(RuntimeError):
    pass


class PersistentWorkerJobError(RuntimeError):
    pass
