from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _load_tool_module(name: str, relative_path: str) -> ModuleType:
    path = Path(relative_path)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def run_slice_tests_module() -> ModuleType:
    return _load_tool_module("run_slice_tests_tool", "tests/tools/run_slice_tests.py")


@pytest.fixture(scope="module")
def run_slice_smoke_module() -> ModuleType:
    return _load_tool_module(
        "run_slice_smoke_tool", "tests/tools/run_slice_smoke_imports.py"
    )


@pytest.fixture(scope="module")
def missing_hint_module() -> ModuleType:
    return _load_tool_module(
        "check_missing_extra_hints_tool", "tests/tools/check_missing_extra_hints.py"
    )


def test_slice_tools_cover_all_declared_extras(
    run_slice_tests_module: ModuleType,
    run_slice_smoke_module: ModuleType,
) -> None:
    import tomllib

    extras = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["tool"][
        "poetry"
    ]["extras"]
    extra_names = set(extras)
    assert set(run_slice_tests_module.SLICE_TESTS) == extra_names
    assert set(run_slice_smoke_module.SLICE_IMPORTS) == extra_names
    assert set(run_slice_smoke_module.SLICE_EXPORTS) == extra_names


def test_run_slice_tests_list_mode_outputs_targets(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    run_slice_tests_module: ModuleType,
) -> None:
    monkeypatch.setattr(
        run_slice_tests_module,
        "_existing_targets",
        lambda targets: targets,
    )
    monkeypatch.setattr("sys.argv", ["run_slice_tests.py", "core", "--list"])

    assert run_slice_tests_module.main() == 0
    out = capsys.readouterr().out
    assert "tests/test_lazy_exports.py" in out


def test_run_slice_tests_executes_pytest_command(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    run_slice_tests_module: ModuleType,
) -> None:
    monkeypatch.setattr(
        run_slice_tests_module,
        "_existing_targets",
        lambda targets: targets[:2],
    )
    called: dict[str, list[str] | None] = {"command": None}

    def fake_call(command):
        called["command"] = command
        return 0

    monkeypatch.setattr(run_slice_tests_module.subprocess, "call", fake_call)
    monkeypatch.setattr(
        "sys.argv", ["run_slice_tests.py", "core", "--", "-q", "-k", "lazy"]
    )

    assert run_slice_tests_module.main() == 0
    assert called["command"] is not None
    assert called["command"][:3] == [
        run_slice_tests_module.sys.executable,
        "-m",
        "pytest",
    ]
    assert "-q" in called["command"]
    assert "lazy" in called["command"]
    assert "Running:" in capsys.readouterr().out


def test_run_slice_smoke_calls_slice_specific_smoke(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    run_slice_smoke_module: ModuleType,
) -> None:
    imported: list[str] = []
    smoke_called = {"value": False}

    class _FakeModule:
        pass

    def fake_import_module(name: str):
        imported.append(name)
        return _FakeModule()

    monkeypatch.setattr(
        run_slice_smoke_module.importlib, "import_module", fake_import_module
    )
    monkeypatch.setattr(
        run_slice_smoke_module,
        "SLICE_IMPORTS",
        {"validation": ["wordlift_sdk.validation"]},
    )
    monkeypatch.setattr(
        run_slice_smoke_module,
        "SLICE_EXPORTS",
        {"validation": [("wordlift_sdk.validation", "validate_file")]},
    )
    monkeypatch.setattr(
        _FakeModule,
        "validate_file",
        object(),
        raising=False,
    )

    def fake_smoke():
        smoke_called["value"] = True

    monkeypatch.setattr(
        run_slice_smoke_module, "SLICE_CALLS", {"validation": fake_smoke}
    )
    monkeypatch.setattr("sys.argv", ["run_slice_smoke_imports.py", "validation"])

    assert run_slice_smoke_module.main() == 0
    assert imported == ["wordlift_sdk.validation", "wordlift_sdk.validation"]
    assert smoke_called["value"] is True
    out = capsys.readouterr().out
    assert "import ok: wordlift_sdk.validation" in out
    assert "export ok: wordlift_sdk.validation.validate_file" in out


def test_missing_extra_hint_checker_accepts_expected_message(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    missing_hint_module: ModuleType,
) -> None:
    checks = [("wordlift_sdk.validation", "validate_file", "validation")]
    monkeypatch.setattr(missing_hint_module, "CHECKS", checks)

    class _FakeModule:
        def __getattr__(self, name: str):
            raise ModuleNotFoundError(
                "wordlift_sdk.validation.validate_file requires optional dependencies "
                "from 'wordlift-sdk[validation]'",
                name="pyshacl",
            )

    monkeypatch.setattr(
        missing_hint_module.importlib,
        "import_module",
        lambda _name: _FakeModule(),
    )

    assert missing_hint_module.main() == 0
    assert "wordlift-sdk[validation]" in capsys.readouterr().out


def test_missing_extra_hint_checker_rejects_missing_hint(
    monkeypatch: pytest.MonkeyPatch,
    missing_hint_module: ModuleType,
) -> None:
    checks = [("wordlift_sdk.validation", "validate_file", "validation")]
    monkeypatch.setattr(missing_hint_module, "CHECKS", checks)

    class _FakeModule:
        def __getattr__(self, name: str):
            raise ModuleNotFoundError("No module named 'pyshacl'", name="pyshacl")

    monkeypatch.setattr(
        missing_hint_module.importlib,
        "import_module",
        lambda _name: _FakeModule(),
    )

    with pytest.raises(AssertionError, match="wordlift-sdk\\[validation\\]"):
        missing_hint_module.main()
