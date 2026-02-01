"""Agent-backed structured data generation."""

from __future__ import annotations

from typing import Callable
from pathlib import Path

from wordlift_sdk.structured_data.agent_generator import (
    AgentGenerator as EngineAgentGenerator,
)


class AgentGenerator:
    """Generates YARRRML and JSON-LD via the agent."""

    def __init__(self, engine: EngineAgentGenerator | None = None) -> None:
        self._engine = engine or EngineAgentGenerator()

    def generate(
        self,
        url: str,
        html: str,
        xhtml: str,
        cleaned_xhtml: str,
        api_key: str,
        dataset_uri: str,
        target_type: str,
        workdir: Path,
        debug: bool,
        max_retries: int,
        max_nesting_depth: int,
        quality_check: bool,
        log: Callable[[str], None],
    ) -> tuple[str, dict]:
        return self._engine.generate_from_agent(
            url,
            html,
            xhtml,
            cleaned_xhtml,
            api_key,
            dataset_uri,
            target_type,
            workdir,
            debug=debug,
            max_retries=max_retries,
            max_nesting_depth=max_nesting_depth,
            quality_check=quality_check,
            log=log,
        )
