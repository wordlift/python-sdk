from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from rdflib import Dataset, Graph, Literal, URIRef

from wordlift_sdk.kg_build.postprocessor_runner import _read_graph_nquads
from wordlift_sdk.kg_build.postprocessors import (
    LoadedPostprocessor,
    PostprocessorContext,
    PostprocessorSpec,
    SubprocessPostprocessor,
    load_postprocessors_for_profile,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def _sample_graph() -> Graph:
    graph = Graph()
    graph.add(
        (
            URIRef("https://example.com/s"),
            URIRef("https://example.com/p"),
            Literal("v"),
        )
    )
    return graph


def _sample_context() -> PostprocessorContext:
    return PostprocessorContext(
        profile_name="test_profile",
        url="https://example.com/page",
        account=object(),
        exports={},
        response=object(),
        settings={},
        ids=None,
    )


def test_manifest_merge_order_and_flags(tmp_path: Path) -> None:
    root = tmp_path
    _write(
        root / "profiles" / "_base" / "postprocessors.toml",
        """
        python = "/base/python"
        timeout_seconds = 11
        keep_temp_on_error = false

        [[postprocessors]]
        class = "test_pp:BaseOne"

        [[postprocessors]]
        class = "test_pp:BaseDisabled"
        enabled = false
        """,
    )
    _write(
        root / "profiles" / "alpha" / "postprocessors.toml",
        """
        timeout_seconds = 17
        keep_temp_on_error = true

        [[postprocessors]]
        class = "test_pp:ProfileOne"
        python = "/profile/python"

        [[postprocessors]]
        class = "test_pp:ProfileTwo"
        """,
    )

    loaded = load_postprocessors_for_profile(root_dir=root, profile_name="alpha")
    assert [item.name for item in loaded] == [
        "test_pp:BaseOne",
        "test_pp:ProfileOne",
        "test_pp:ProfileTwo",
    ]

    first = loaded[0].handler
    second = loaded[1].handler
    third = loaded[2].handler
    assert isinstance(first, SubprocessPostprocessor)
    assert isinstance(second, SubprocessPostprocessor)
    assert isinstance(third, SubprocessPostprocessor)
    assert first.spec.python == "/base/python"
    assert first.spec.timeout_seconds == 11
    assert first.spec.keep_temp_on_error is False
    assert second.spec.python == "/profile/python"
    assert second.spec.timeout_seconds == 17
    assert second.spec.keep_temp_on_error is True
    assert third.spec.python == "./.venv/bin/python"
    assert third.spec.timeout_seconds == 17
    assert third.spec.keep_temp_on_error is True


def test_subprocess_execution_and_nquads_exchange(tmp_path: Path) -> None:
    root = tmp_path
    _write(
        root / "test_pp.py",
        """
        from rdflib import Literal, URIRef

        class AddTriple:
            def process_graph(self, graph, context):
                graph.add(
                    (
                        URIRef("https://example.com/new-s"),
                        URIRef("https://example.com/new-p"),
                        Literal("new-v"),
                    )
                )
                return graph
        """,
    )
    spec = PostprocessorSpec(
        class_path="test_pp:AddTriple",
        python=sys.executable,
        timeout_seconds=30,
        enabled=True,
        keep_temp_on_error=False,
    )
    processor = SubprocessPostprocessor(spec=spec, root_dir=root)

    output = processor.process_graph(_sample_graph(), _sample_context())
    assert output is not None
    assert len(output) == 2
    assert (
        URIRef("https://example.com/new-s"),
        URIRef("https://example.com/new-p"),
        Literal("new-v"),
    ) in output


def test_runner_module_is_runnable_via_python_m(tmp_path: Path) -> None:
    root = tmp_path
    _write(
        root / "test_pp.py",
        """
        from rdflib import Literal, URIRef

        class AddRunnerTriple:
            def process_graph(self, graph, context):
                graph.add(
                    (
                        URIRef("https://example.com/runner-s"),
                        URIRef("https://example.com/runner-p"),
                        Literal(context.profile_name),
                    )
                )
                return graph
        """,
    )

    input_graph = _sample_graph()
    input_path = root / "input.nq"
    output_path = root / "output.nq"
    context_path = root / "context.json"

    dataset_graph = Dataset()
    for triple in input_graph:
        dataset_graph.add(triple)
    dataset_graph.serialize(destination=input_path, format="nquads")

    context_path.write_text(
        json.dumps(
            {
                "profile_name": "runner_profile",
                "url": "https://example.com/page",
                "dataset_uri": "https://data.example.com",
                "country_code": "us",
                "exports": {},
                "settings": {},
                "response": {"id": "id-1", "web_page": {"url": "", "html": ""}},
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "wordlift_sdk.kg_build.postprocessor_runner",
            "--class",
            "test_pp:AddRunnerTriple",
            "--input-graph",
            str(input_path),
            "--output-graph",
            str(output_path),
            "--context",
            str(context_path),
        ],
        cwd=str(root),
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert output_path.exists()

    output_graph = _read_graph_nquads(output_path)
    assert (
        URIRef("https://example.com/runner-s"),
        URIRef("https://example.com/runner-p"),
        Literal("runner_profile"),
    ) in output_graph


def test_timeout_seconds_is_enforced(tmp_path: Path) -> None:
    root = tmp_path
    _write(
        root / "test_pp.py",
        """
        import time

        class SlowPostprocessor:
            def process_graph(self, graph, context):
                time.sleep(2.0)
                return graph
        """,
    )
    spec = PostprocessorSpec(
        class_path="test_pp:SlowPostprocessor",
        python=sys.executable,
        timeout_seconds=1,
        enabled=True,
        keep_temp_on_error=False,
    )
    processor = SubprocessPostprocessor(spec=spec, root_dir=root)

    with pytest.raises(subprocess.TimeoutExpired):
        processor.process_graph(_sample_graph(), _sample_context())


def test_keep_temp_on_error_preserves_debug_files(tmp_path: Path) -> None:
    root = tmp_path
    _write(
        root / "test_pp.py",
        """
        class BrokenPostprocessor:
            def process_graph(self, graph, context):
                raise RuntimeError("boom")
        """,
    )
    class_path = "test_pp:BrokenPostprocessor"
    spec = PostprocessorSpec(
        class_path=class_path,
        python=sys.executable,
        timeout_seconds=30,
        enabled=True,
        keep_temp_on_error=True,
    )
    processor = SubprocessPostprocessor(spec=spec, root_dir=root)

    with pytest.raises(RuntimeError):
        processor.process_graph(_sample_graph(), _sample_context())

    debug_target = (
        root
        / "output"
        / "postprocessor_debug"
        / class_path.replace(":", "_").replace(".", "_")
    )
    assert debug_target.exists()
    assert (debug_target / "input_graph.nq").exists()
    assert (debug_target / "context.json").exists()


def test_fail_fast_stops_after_first_postprocessor_error() -> None:
    class RaiseFirst:
        def process_graph(self, graph: Graph, context: PostprocessorContext) -> Graph:
            raise RuntimeError("first failed")

    class ShouldNotRun:
        called = False

        def process_graph(self, graph: Graph, context: PostprocessorContext) -> Graph:
            self.called = True
            return graph

    second = ShouldNotRun()
    chain = [
        LoadedPostprocessor(name="first", handler=RaiseFirst()),
        LoadedPostprocessor(name="second", handler=second),
    ]

    with pytest.raises(RuntimeError, match="first failed"):
        graph = _sample_graph()
        context = _sample_context()
        for processor in chain:
            graph = processor.run(graph, context)

    assert second.called is False


def test_subprocess_uses_inherited_environment_without_pythonpath_injection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path
    spec = PostprocessorSpec(
        class_path="test_pp:AddTriple",
        python=sys.executable,
        timeout_seconds=30,
        enabled=True,
        keep_temp_on_error=False,
    )
    processor = SubprocessPostprocessor(spec=spec, root_dir=root)
    captured: dict[str, object] = {}

    def fake_run(*args, **kwargs):
        captured["kwargs"] = kwargs
        cmd = args[0]
        output_flag_index = cmd.index("--output-graph")
        output_path = Path(cmd[output_flag_index + 1])
        output_path.write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = processor.process_graph(_sample_graph(), _sample_context())
    assert output is not None

    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert "env" not in kwargs
