"""Debug output helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable


def echo_debug(debug_path: Path, log: Callable[[str], None]) -> None:
    if not debug_path.exists():
        return
    try:
        payload = json.loads(debug_path.read_text())
    except Exception:
        log(f"Debug output written to {debug_path}")
        return
    prompt = payload.get("prompt", "")
    response = payload.get("response")
    log("--- Agent prompt ---")
    log(prompt)
    log("--- Agent response ---")
    log(json.dumps(response, indent=2))
