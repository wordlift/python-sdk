"""Extract Search Gallery samples into test fixtures.

This script downloads Google Search Gallery feature pages, copies all sample code
blocks, and materializes parseable JSON-LD samples for validation tests.
"""

from __future__ import annotations

import json
import re
import shutil
from html import unescape
from pathlib import Path

import requests

from wordlift_sdk.validation.generator import (
    SEARCH_GALLERY_URL,
    _feature_urls_from_gallery,
)

PRE_RE = re.compile(r"<pre([^>]*)>(.*?)</pre>", re.IGNORECASE | re.DOTALL)
TEXTAREA_RE = re.compile(
    r'<textarea[^>]*name="code_snippet"[^>]*>(.*?)</textarea>',
    re.IGNORECASE | re.DOTALL,
)
SCRIPT_JSONLD_RE = re.compile(
    r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")
LABEL_RE = re.compile(r'data-label="([^"]+)"', re.IGNORECASE)


def _strip_tags(value: str) -> str:
    return unescape(TAG_RE.sub("", value)).strip()


def _safe_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "sample"


def _extract_pre_samples(html: str) -> list[tuple[str, str]]:
    samples: list[tuple[str, str]] = []
    for attrs, body in PRE_RE.findall(html):
        label_match = LABEL_RE.search(attrs)
        label = label_match.group(1).strip() if label_match else "pre"
        text = _strip_tags(body)
        if not text:
            continue
        samples.append((label, text))
    return samples


def _extract_textarea_samples(html: str) -> list[str]:
    return [
        unescape(match).strip() for match in TEXTAREA_RE.findall(html) if match.strip()
    ]


def _extract_jsonld_from_snippet(snippet: str) -> list[dict | list]:
    payloads: list[dict | list] = []
    for raw in SCRIPT_JSONLD_RE.findall(snippet):
        raw = raw.strip()
        if not raw:
            continue
        parsed = _parse_json(raw)
        if parsed is not None:
            payloads.append(parsed)
    return payloads


def _extract_page_jsonld_scripts(html: str) -> list[dict | list]:
    payloads: list[dict | list] = []
    for raw in SCRIPT_JSONLD_RE.findall(html):
        raw = raw.strip()
        if not raw:
            continue
        parsed = _parse_json(raw)
        if parsed is not None:
            payloads.append(parsed)
    return payloads


def _extract_jsonld_from_pre_text(text: str) -> list[dict | list]:
    payloads = _extract_jsonld_from_snippet(text)
    if payloads:
        return payloads
    candidate = text.strip()
    if candidate.startswith(("{", "[")):
        parsed = _parse_json(candidate)
        if parsed is not None:
            return [parsed]
    return []


def _parse_json(raw: str) -> dict | list | None:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    sanitized = re.sub(r"^\s*//.*$", "", raw, flags=re.MULTILINE)
    sanitized = re.sub(r"/\*.*?\*/", "", sanitized, flags=re.DOTALL)
    sanitized = re.sub(r"^\s*\.\.\.\s*$", "", sanitized, flags=re.MULTILINE)
    sanitized = re.sub(r",\s*([}\]])", r"\1", sanitized)
    sanitized = _normalize_newlines_in_strings(sanitized)
    sanitized = sanitized.strip()
    if not sanitized:
        return None
    try:
        return json.loads(sanitized)
    except json.JSONDecodeError:
        return None


def _normalize_newlines_in_strings(value: str) -> str:
    out: list[str] = []
    in_string = False
    escaped = False
    for ch in value:
        if in_string:
            if escaped:
                out.append(ch)
                escaped = False
                continue
            if ch == "\\":
                out.append(ch)
                escaped = True
                continue
            if ch == '"':
                out.append(ch)
                in_string = False
                continue
            if ch in {"\n", "\r"}:
                out.append(" ")
                continue
            out.append(ch)
            continue
        out.append(ch)
        if ch == '"':
            in_string = True
    return "".join(out)


def _fetch_search_gallery_pages() -> dict[str, str]:
    html = requests.get(SEARCH_GALLERY_URL, timeout=30).text
    pages: dict[str, str] = {}
    for url in _feature_urls_from_gallery(html):
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        pages[slug] = url
    return pages


def main() -> int:
    fixtures_root = Path("tests/fixtures/search_gallery")
    if fixtures_root.exists():
        shutil.rmtree(fixtures_root)
    fixtures_root.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, dict[str, object]] = {}
    pages = _fetch_search_gallery_pages()

    for slug, url in pages.items():
        html = requests.get(url, timeout=30).text
        page_root = fixtures_root / slug
        raw_dir = page_root / "raw"
        jsonld_dir = page_root / "jsonld"
        raw_dir.mkdir(parents=True, exist_ok=True)
        jsonld_dir.mkdir(parents=True, exist_ok=True)

        raw_paths: list[str] = []
        json_entries: list[dict[str, str]] = []
        seen_raw: set[str] = set()
        seen_json: set[str] = set()

        pre_samples = _extract_pre_samples(html)
        for idx, (label, text) in enumerate(pre_samples, start=1):
            dedupe_key = f"{label}\n{text}"
            if dedupe_key in seen_raw:
                continue
            seen_raw.add(dedupe_key)
            raw_name = f"{idx:03d}-{_safe_slug(label)}.txt"
            raw_path = raw_dir / raw_name
            raw_path.write_text(text + "\n", encoding="utf-8")
            raw_paths.append(raw_path.as_posix())

            for payload_idx, payload in enumerate(
                _extract_jsonld_from_pre_text(text), start=1
            ):
                normalized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
                if normalized in seen_json:
                    continue
                seen_json.add(normalized)
                json_name = f"{idx:03d}-{_safe_slug(label)}-{payload_idx:02d}.jsonld"
                json_path = jsonld_dir / json_name
                json_path.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                json_entries.append(
                    {
                        "id": json_name.rsplit(".", 1)[0],
                        "path": json_path.as_posix(),
                        "source_kind": "pre",
                        "label": label,
                    }
                )

        textarea_samples = _extract_textarea_samples(html)
        for idx, snippet in enumerate(textarea_samples, start=1):
            raw_name = f"ta-{idx:03d}.html"
            raw_path = raw_dir / raw_name
            raw_path.write_text(snippet + "\n", encoding="utf-8")
            raw_paths.append(raw_path.as_posix())

            for payload_idx, payload in enumerate(
                _extract_jsonld_from_snippet(snippet), start=1
            ):
                normalized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
                if normalized in seen_json:
                    continue
                seen_json.add(normalized)
                json_name = f"ta-{idx:03d}-{payload_idx:02d}.jsonld"
                json_path = jsonld_dir / json_name
                json_path.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                json_entries.append(
                    {
                        "id": json_name.rsplit(".", 1)[0],
                        "path": json_path.as_posix(),
                        "source_kind": "textarea",
                        "label": f"textarea-{idx:03d}",
                    }
                )

        for payload_idx, payload in enumerate(
            _extract_page_jsonld_scripts(html), start=1
        ):
            normalized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
            if normalized in seen_json:
                continue
            seen_json.add(normalized)
            json_name = f"pg-{payload_idx:03d}.jsonld"
            json_path = jsonld_dir / json_name
            json_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            json_entries.append(
                {
                    "id": json_name.rsplit(".", 1)[0],
                    "path": json_path.as_posix(),
                    "source_kind": "page_script",
                    "label": f"page-script-{payload_idx:03d}",
                }
            )

        manifest[slug] = {
            "url": url,
            "raw_samples": raw_paths,
            "jsonld_samples": json_entries,
        }

    manifest_path = fixtures_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
