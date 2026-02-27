from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass


_AUTO_ORDER = ("claude", "codex", "gemini")
_SUPPORTED = frozenset(_AUTO_ORDER)


@dataclass(frozen=True)
class AgentCliResult:
    cli: str
    output: str


class AgentCliError(RuntimeError):
    pass


class LocalAgentCliRunner:
    """Run local agent CLIs in non-interactive mode and parse JSON output."""

    def __init__(
        self,
        cli: str | None = None,
        *,
        timeout_sec: float = 120.0,
    ) -> None:
        self._timeout_sec = timeout_sec
        self._cli, self._binary = self._resolve_cli(cli)

    @property
    def cli(self) -> str:
        return self._cli

    def run(self, prompt: str) -> AgentCliResult:
        attempts: list[str] = []
        for cmd in self._candidate_commands(prompt):
            try:
                completed = subprocess.run(
                    cmd,
                    text=True,
                    capture_output=True,
                    timeout=self._timeout_sec,
                    check=False,
                )
            except FileNotFoundError as exc:
                attempts.append(f"{' '.join(cmd)} -> command not found ({exc})")
                continue
            except subprocess.TimeoutExpired as exc:
                attempts.append(
                    f"{' '.join(cmd)} -> timeout after {self._timeout_sec}s ({exc})"
                )
                continue

            if completed.returncode != 0:
                stderr = (completed.stderr or "").strip()
                attempts.append(
                    f"{' '.join(cmd)} -> exit {completed.returncode}: {stderr}"
                )
                continue

            output = (completed.stdout or "").strip()
            if output:
                return AgentCliResult(cli=self._cli, output=output)
            attempts.append(f"{' '.join(cmd)} -> empty stdout")

        details = "\n".join(attempts)
        raise AgentCliError(
            f"Failed to run local agent CLI '{self._cli}'. Tried:\n{details}"
        )

    def run_json(self, prompt: str) -> dict[str, object]:
        result = self.run(prompt)
        parsed = _extract_json_object(result.output)
        if parsed is None:
            raise AgentCliError(f"Agent CLI '{result.cli}' returned non-JSON output.")
        return parsed

    def _resolve_cli(self, cli: str | None) -> tuple[str, str]:
        if cli:
            normalized = cli.strip().lower()
            if normalized not in _SUPPORTED:
                supported = ", ".join(sorted(_SUPPORTED))
                raise AgentCliError(
                    f"Unsupported agent_cli '{cli}'. Supported values: {supported}."
                )
            resolved = shutil.which(normalized)
            if not resolved:
                raise AgentCliError(
                    f"Local agent CLI binary '{normalized}' was not found in PATH."
                )
            return normalized, resolved

        for candidate in _AUTO_ORDER:
            resolved = shutil.which(candidate)
            if resolved:
                return candidate, resolved
        raise AgentCliError(
            "No supported local agent CLI found in PATH. "
            "Install one of: claude, codex, gemini."
        )

    def _candidate_commands(self, prompt: str) -> list[list[str]]:
        if self._cli == "claude":
            return [
                [self._binary, "-p", "--output-format", "json", prompt],
                [self._binary, "-p", prompt],
            ]
        if self._cli == "codex":
            return [
                [self._binary, "exec", prompt],
                [self._binary, "-p", prompt],
            ]
        return [
            [self._binary, "-p", prompt],
            [self._binary, prompt],
        ]


def _extract_json_object(text: str) -> dict[str, object] | None:
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
    if fenced:
        try:
            loaded = json.loads(fenced.group(1))
            if isinstance(loaded, dict):
                return loaded
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        loaded = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(loaded, dict):
        return None
    return loaded


__all__ = ["AgentCliError", "AgentCliResult", "LocalAgentCliRunner"]
