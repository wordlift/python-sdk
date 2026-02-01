"""Request/response models for structured data workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class CreateRequest:
    url: str
    target_type: str
    output_dir: Path
    base_name: str
    jsonld_path: Path | None
    yarrml_path: Path | None
    api_key: str | None
    base_url: str | None
    debug: bool
    headed: bool
    timeout_ms: int
    max_retries: int
    quality_check: bool
    max_xhtml_chars: int
    max_text_node_chars: int
    max_nesting_depth: int
    verbose: bool
    validate: bool
    wait_until: str


@dataclass
class GenerateRequest:
    input_value: str
    yarrrml_path: Path
    regex: str
    output_dir: Path
    output_format: str
    concurrency: str
    api_key: str | None
    base_url: str | None
    headed: bool
    timeout_ms: int
    wait_until: str
    max_xhtml_chars: int
    max_text_node_chars: int
    max_pages: int | None
    verbose: bool
