from __future__ import annotations

from types import SimpleNamespace

import pytest

from wordlift_sdk.agent_cli import AgentCliError, LocalAgentCliRunner


def test_runner_auto_picks_first_available_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "wordlift_sdk.agent_cli.local.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in ("claude", "codex") else None,
    )
    runner = LocalAgentCliRunner()
    assert runner.cli == "claude"


def test_runner_requires_supported_cli_and_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(AgentCliError, match="Unsupported agent_cli"):
        LocalAgentCliRunner(cli="foo")

    monkeypatch.setattr("wordlift_sdk.agent_cli.local.shutil.which", lambda _: None)
    with pytest.raises(AgentCliError, match="was not found in PATH"):
        LocalAgentCliRunner(cli="codex")


def test_runner_executes_and_extracts_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "wordlift_sdk.agent_cli.local.shutil.which", lambda _: "/usr/bin/claude"
    )

    def _fake_run(*args, **kwargs):
        del args, kwargs
        return SimpleNamespace(
            returncode=0,
            stdout='{"main_type":"Article","additional_types":["NewsArticle"],"explanation":"fit"}',
            stderr="",
        )

    monkeypatch.setattr("wordlift_sdk.agent_cli.local.subprocess.run", _fake_run)
    payload = LocalAgentCliRunner(cli="claude").run_json("prompt")
    assert payload["main_type"] == "Article"


def test_runner_raises_when_all_candidates_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "wordlift_sdk.agent_cli.local.shutil.which", lambda _: "/usr/bin/gemini"
    )

    def _fake_run(*args, **kwargs):
        del args, kwargs
        return SimpleNamespace(returncode=1, stdout="", stderr="bad")

    monkeypatch.setattr("wordlift_sdk.agent_cli.local.subprocess.run", _fake_run)

    with pytest.raises(AgentCliError, match="Failed to run local agent CLI"):
        LocalAgentCliRunner(cli="gemini").run("prompt")
