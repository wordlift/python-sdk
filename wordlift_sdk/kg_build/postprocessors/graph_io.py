from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rdflib import Dataset, Graph

from .types import Closeable, LoadedPostprocessor, PostprocessorContext


def _build_runner_payload(context: PostprocessorContext) -> dict[str, Any]:
    account = getattr(context, "account", None)
    dataset_uri = str(getattr(account, "dataset_uri", "")).rstrip("/")
    country_code = str(getattr(account, "country_code", "")).strip().lower()
    account_key = (
        str(context.account_key).strip()
        if getattr(context, "account_key", None) is not None
        else ""
    )
    profile = dict(getattr(context, "profile", {}) or {})
    if "settings" not in profile or not isinstance(profile.get("settings"), dict):
        profile["settings"] = {}
    profile_settings = dict(profile.get("settings", {}) or {})
    profile_settings.setdefault("api_url", "https://api.wordlift.io")
    profile["settings"] = profile_settings
    response = getattr(context, "response", None)
    web_page = getattr(response, "web_page", None) if response else None
    return {
        "profile_name": context.profile_name,
        "profile": profile,
        "url": context.url,
        "dataset_uri": dataset_uri,
        "country_code": country_code,
        "account_key": account_key or None,
        "exports": context.exports,
        "existing_web_page_id": context.existing_web_page_id,
        "response": {
            "id": getattr(response, "id", None) or context.existing_web_page_id,
            "web_page": {
                "url": getattr(web_page, "url", None),
                "html": getattr(web_page, "html", None),
            },
        },
    }


def close_loaded_postprocessors(postprocessors: list[LoadedPostprocessor]) -> None:
    for processor in postprocessors:
        if isinstance(processor.handler, Closeable):
            processor.handler.close()


def _write_graph_nquads(graph: Graph, path: Path) -> None:
    dataset = Dataset()
    for triple in graph:
        dataset.add(triple)
    dataset.serialize(destination=path, format="nquads")


def _read_graph_nquads(path: Path) -> Graph:
    dataset = Dataset()
    dataset.parse(path, format="nquads")
    graph = Graph()
    for triple in dataset.triples((None, None, None)):
        graph.add(triple)
    return graph


def _redact_debug_context(path: Path) -> None:
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(payload, dict):
        return
    if payload.get("account_key"):
        payload["account_key"] = "***REDACTED***"
    profile = payload.get("profile")
    if isinstance(profile, dict) and profile.get("api_key"):
        profile["api_key"] = "***REDACTED***"
    settings = (
        profile.get("settings")
        if isinstance(profile, dict) and isinstance(profile.get("settings"), dict)
        else None
    )
    if settings and settings.get("api_key"):
        settings["api_key"] = "***REDACTED***"
    if settings and settings.get("wordlift_key"):
        settings["wordlift_key"] = "***REDACTED***"
    if settings and settings.get("WORDLIFT_KEY"):
        settings["WORDLIFT_KEY"] = "***REDACTED***"
    if settings and settings.get("WORDLIFT_API_KEY"):
        settings["WORDLIFT_API_KEY"] = "***REDACTED***"
    payload["profile"] = profile
    path.write_text(
        json.dumps(payload, ensure_ascii=True, default=str),
        encoding="utf-8",
    )
