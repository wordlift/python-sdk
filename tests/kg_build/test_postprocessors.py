from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest
from rdflib import Dataset, Graph, Literal, URIRef

from wordlift_sdk.kg_build.postprocessor_runner import (
    _build_context,
    _read_graph_nquads,
)
from wordlift_sdk.kg_build.postprocessors import (
    LoadedPostprocessor,
    PostprocessorContext,
    PostprocessorSpec,
    SubprocessPostprocessor,
    _build_runner_payload,
    close_loaded_postprocessors,
    load_postprocessors_for_profile,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_current_pythonpath = os.environ.get("PYTHONPATH", "")
if _current_pythonpath:
    os.environ["PYTHONPATH"] = f"{PROJECT_ROOT}{os.pathsep}{_current_pythonpath}"
else:
    os.environ["PYTHONPATH"] = str(PROJECT_ROOT)


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


def _sample_context(
    *,
    account_key: str | None = "test-key",
    profile: dict[str, object] | None = None,
) -> PostprocessorContext:
    profile_payload = {
        "name": "test_profile",
        "settings": {"api_url": "https://api.wordlift.io"},
    }
    if profile:
        profile_payload.update(profile)
    return PostprocessorContext(
        profile_name="test_profile",
        profile=profile_payload,
        url="https://example.com/page",
        account=SimpleNamespace(
            dataset_uri="https://data.example.com",
            country_code="us",
        ),
        account_key=account_key,
        exports={},
        response=SimpleNamespace(
            id="id-1",
            web_page=SimpleNamespace(
                url="https://example.com/page", html="<html></html>"
            ),
        ),
        existing_web_page_id=None,
        ids=None,
    )


def test_build_runner_payload_includes_account_key_and_default_api_url() -> None:
    payload = _build_runner_payload(
        _sample_context(
            account_key="secret-key",
            profile={"settings": {}},
        )
    )
    assert payload["account_key"] == "secret-key"
    assert payload["profile"]["settings"]["api_url"] == "https://api.wordlift.io"


def test_build_context_restores_account_key_and_default_api_url() -> None:
    context = _build_context(
        {
            "profile_name": "runner_profile",
            "url": "https://example.com/page",
            "dataset_uri": "https://data.example.com/",
            "country_code": "US",
            "account_key": "secret-key",
            "exports": {},
            "profile": {"name": "runner_profile", "settings": {}},
            "response": {"id": "id-1", "web_page": {"url": "", "html": ""}},
        }
    )
    assert context.account_key == "secret-key"
    assert context.profile["settings"]["api_url"] == "https://api.wordlift.io"


def test_build_context_accepts_missing_account_key() -> None:
    context = _build_context(
        {
            "profile_name": "runner_profile",
            "url": "https://example.com/page",
            "dataset_uri": "https://data.example.com/",
            "country_code": "US",
            "exports": {},
            "profile": {
                "name": "runner_profile",
                "settings": {"api_url": "https://profile.example.com"},
            },
            "response": {"id": "id-1", "web_page": {"url": "", "html": ""}},
        }
    )
    assert context.account_key is None
    assert context.profile["settings"]["api_url"] == "https://profile.example.com"


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


def test_manifest_runtime_selection(tmp_path: Path) -> None:
    root = tmp_path
    _write(
        root / "profiles" / "_base" / "postprocessors.toml",
        """
        [[postprocessors]]
        class = "test_pp:BaseOne"
        """,
    )
    _write(
        root / "profiles" / "alpha" / "postprocessors.toml",
        """
        [[postprocessors]]
        class = "test_pp:ProfileOne"
        """,
    )

    loaded = load_postprocessors_for_profile(
        root_dir=root,
        profile_name="alpha",
        runtime="persistent",
    )
    assert len(loaded) == 2
    assert isinstance(loaded[0].handler, SubprocessPostprocessor)
    assert loaded[0].handler.runtime == "persistent"
    assert loaded[1].handler.runtime == "persistent"


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


def test_persistent_runtime_reuses_postprocessor_instance(tmp_path: Path) -> None:
    root = tmp_path
    _write(
        root / "test_pp.py",
        """
        from rdflib import Literal, URIRef

        class StatefulPostprocessor:
            def __init__(self):
                self.calls = 0

            def process_graph(self, graph, context):
                self.calls += 1
                graph.set(
                    (
                        URIRef("https://example.com/state-s"),
                        URIRef("https://example.com/state-p"),
                        Literal(self.calls),
                    )
                )
                return graph
        """,
    )
    spec = PostprocessorSpec(
        class_path="test_pp:StatefulPostprocessor",
        python=sys.executable,
        timeout_seconds=30,
        enabled=True,
        keep_temp_on_error=False,
    )
    processor = SubprocessPostprocessor(
        spec=spec,
        root_dir=root,
        runtime="persistent",
    )

    first = processor.process_graph(_sample_graph(), _sample_context())
    second = processor.process_graph(_sample_graph(), _sample_context())
    processor.close()

    assert first is not None
    assert second is not None
    assert (
        URIRef("https://example.com/state-s"),
        URIRef("https://example.com/state-p"),
        Literal(1),
    ) in first
    assert (
        URIRef("https://example.com/state-s"),
        URIRef("https://example.com/state-p"),
        Literal(2),
    ) in second


@pytest.mark.parametrize("runtime", ["oneshot", "persistent"])
def test_postprocessor_context_exposes_account_key_and_profile_api_url(
    tmp_path: Path, runtime: str
) -> None:
    root = tmp_path
    _write(
        root / "test_pp.py",
        """
        from rdflib import Literal, URIRef

        class ReadAuthContext:
            def process_graph(self, graph, context):
                graph.set(
                    (
                        URIRef("https://example.com/auth"),
                        URIRef("https://example.com/account_key"),
                        Literal(context.account_key or ""),
                    )
                )
                graph.set(
                    (
                        URIRef("https://example.com/auth"),
                        URIRef("https://example.com/api_url"),
                        Literal(context.profile.get("settings", {}).get("api_url", "")),
                    )
                )
                return graph
        """,
    )
    spec = PostprocessorSpec(
        class_path="test_pp:ReadAuthContext",
        python=sys.executable,
        timeout_seconds=30,
        enabled=True,
        keep_temp_on_error=False,
    )
    processor = SubprocessPostprocessor(spec=spec, root_dir=root, runtime=runtime)
    try:
        output = processor.process_graph(
            _sample_graph(),
            _sample_context(
                account_key="secret-key",
                profile={"settings": {"api_url": "https://profile-api.example.com"}},
            ),
        )
    finally:
        processor.close()

    assert output is not None
    assert (
        URIRef("https://example.com/auth"),
        URIRef("https://example.com/account_key"),
        Literal("secret-key"),
    ) in output
    assert (
        URIRef("https://example.com/auth"),
        URIRef("https://example.com/api_url"),
        Literal("https://profile-api.example.com"),
    ) in output


@pytest.mark.parametrize("runtime", ["oneshot", "persistent"])
def test_postprocessor_context_defaults_api_url_when_missing(
    tmp_path: Path, runtime: str
) -> None:
    root = tmp_path
    _write(
        root / "test_pp.py",
        """
        from rdflib import Literal, URIRef

        class ReadDefaultApiUrl:
            def process_graph(self, graph, context):
                graph.set(
                    (
                        URIRef("https://example.com/auth"),
                        URIRef("https://example.com/api_url"),
                        Literal(context.profile.get("settings", {}).get("api_url", "")),
                    )
                )
                return graph
        """,
    )
    spec = PostprocessorSpec(
        class_path="test_pp:ReadDefaultApiUrl",
        python=sys.executable,
        timeout_seconds=30,
        enabled=True,
        keep_temp_on_error=False,
    )
    processor = SubprocessPostprocessor(spec=spec, root_dir=root, runtime=runtime)
    try:
        output = processor.process_graph(
            _sample_graph(),
            _sample_context(account_key="secret-key", profile={"settings": {}}),
        )
    finally:
        processor.close()

    assert output is not None
    assert (
        URIRef("https://example.com/auth"),
        URIRef("https://example.com/api_url"),
        Literal("https://api.wordlift.io"),
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
                "profile": {"name": "runner_profile", "settings": {}},
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


def test_timeout_seconds_is_enforced_in_persistent_runtime(tmp_path: Path) -> None:
    root = tmp_path
    _write(
        root / "test_pp.py",
        """
        import time

        class SlowPersistentPostprocessor:
            def process_graph(self, graph, context):
                time.sleep(2.0)
                return graph
        """,
    )
    spec = PostprocessorSpec(
        class_path="test_pp:SlowPersistentPostprocessor",
        python=sys.executable,
        timeout_seconds=1,
        enabled=True,
        keep_temp_on_error=False,
    )
    processor = SubprocessPostprocessor(
        spec=spec,
        root_dir=root,
        runtime="persistent",
    )

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


def test_keep_temp_on_error_redacts_account_key_in_debug_context(
    tmp_path: Path,
) -> None:
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
    secret = "top-secret-key"

    with pytest.raises(RuntimeError):
        processor.process_graph(_sample_graph(), _sample_context(account_key=secret))

    context_path = (
        root
        / "output"
        / "postprocessor_debug"
        / class_path.replace(":", "_").replace(".", "_")
        / "context.json"
    )
    context_doc = json.loads(context_path.read_text(encoding="utf-8"))
    assert context_doc["account_key"] == "***REDACTED***"
    assert secret not in context_path.read_text(encoding="utf-8")


def test_account_key_is_never_written_to_logs(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    root = tmp_path
    _write(
        root / "profiles" / "_base" / "postprocessors.toml",
        """
        [[postprocessors]]
        class = "test_pp:BaseOne"
        """,
    )
    secret = "top-secret-key"

    caplog.set_level(logging.INFO)
    _ = _build_runner_payload(_sample_context(account_key=secret))
    load_postprocessors_for_profile(root_dir=root, profile_name="alpha")

    assert secret not in caplog.text


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


def test_close_loaded_postprocessors_calls_handler_close() -> None:
    class Closable:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

        def process_graph(self, graph: Graph, context: PostprocessorContext) -> Graph:
            return graph

    handler = Closable()
    loaded = [LoadedPostprocessor(name="x", handler=handler)]
    close_loaded_postprocessors(loaded)
    assert handler.closed is True
