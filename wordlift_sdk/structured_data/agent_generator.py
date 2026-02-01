"""Agent-backed generation utilities."""

from __future__ import annotations

from .engine import generate_from_agent


class AgentGenerator:
    """Agent-backed generation utilities."""

    def generate_from_agent(self, *args, **kwargs):
        return generate_from_agent(*args, **kwargs)
