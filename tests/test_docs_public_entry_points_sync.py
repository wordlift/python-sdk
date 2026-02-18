from __future__ import annotations

import re
from pathlib import Path


def _extract_yaml_block(text: str) -> str:
    match = re.search(r"```yaml\n(.*?)\n```", text, re.DOTALL)
    assert match, "Missing YAML metadata block in docs/public_entry_points.md"
    return match.group(1)


def _parse_method_entries(yaml_text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for block in re.finditer(
        r"\n  - id: (.*?)(?=\n  - id: |\Z)", "\n" + yaml_text, re.DOTALL
    ):
        item = block.group(1)
        id_match = re.search(r"^([^\n]+)", item, re.MULTILINE)
        file_match = re.search(r"\n\s+file:\s+([^\n]+)", item)
        signature_match = re.search(r"\n\s+signature:\s+([^\n]+)", item)
        if not (id_match and file_match and signature_match):
            continue
        entries.append(
            {
                "id": id_match.group(1).strip(),
                "file": file_match.group(1).strip(),
                "signature": signature_match.group(1).strip(),
            }
        )
    return entries


def _symbol_from_signature(signature: str) -> str:
    head = signature.split("(", 1)[0].strip()
    if "." in head:
        return head.split(".")[-1]
    return head


def _symbol_exists(module_text: str, symbol: str) -> bool:
    if re.search(rf"^\s*def\s+{re.escape(symbol)}\s*\(", module_text, re.MULTILINE):
        return True
    if re.search(
        rf"^\s*async\s+def\s+{re.escape(symbol)}\s*\(",
        module_text,
        re.MULTILINE,
    ):
        return True
    if re.search(rf"^\s*class\s+{re.escape(symbol)}\b", module_text, re.MULTILINE):
        return True
    return False


def test_public_entry_points_metadata_targets_real_symbols() -> None:
    doc_path = Path("docs/public_entry_points.md")
    assert doc_path.exists(), "docs/public_entry_points.md is missing"
    doc_text = doc_path.read_text(encoding="utf-8")
    yaml_text = _extract_yaml_block(doc_text)
    entries = _parse_method_entries(yaml_text)

    assert entries, "No metadata entries parsed from YAML block"

    for entry in entries:
        file_path = Path(entry["file"])
        assert file_path.exists(), f"Missing file for {entry['id']}: {file_path}"
        module_text = file_path.read_text(encoding="utf-8")
        symbol = _symbol_from_signature(entry["signature"])
        assert _symbol_exists(module_text, symbol), (
            f"Symbol '{symbol}' not found for {entry['id']} in {file_path}"
        )
