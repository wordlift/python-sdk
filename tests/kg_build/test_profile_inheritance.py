from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from rdflib import Literal, URIRef

from wordlift_sdk.kg_build.config.loader import load_profile_config
from wordlift_sdk.kg_build.protocol import ProfileImportProtocol


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def _context() -> SimpleNamespace:
    return SimpleNamespace(
        account=SimpleNamespace(dataset_uri="https://data.example.com/dataset"),
        client_configuration=SimpleNamespace(api_key={}),
        configuration_provider=SimpleNamespace(
            get_value=lambda *_args, **_kwargs: None
        ),
    )


def test_runtime_inherits_from_base_when_selected_missing(tmp_path: Path) -> None:
    _write(
        tmp_path / "worai.toml",
        """
        [profiles._base]
        postprocessor_runtime = "persistent"

        [profiles.alpha]
        """,
    )

    config = load_profile_config(tmp_path / "worai.toml")
    profile = config.get("alpha")
    protocol = ProfileImportProtocol(
        context=_context(),
        profile=profile,
        root_dir=tmp_path,
    )

    assert profile.settings["postprocessor_runtime"] == "persistent"
    assert protocol._postprocessor_runtime == "persistent"


def test_template_override_prefers_selected_relative_path(tmp_path: Path) -> None:
    _write(
        tmp_path / "worai.toml",
        """
        [profiles._base]

        [profiles.alpha]
        """,
    )
    _write(
        tmp_path / "profiles" / "_base" / "templates" / "entity.ttl",
        """
        @prefix ex: <https://example.com/> .
        ex:s ex:p "base" .
        """,
    )
    _write(
        tmp_path / "profiles" / "alpha" / "templates" / "entity.ttl",
        """
        @prefix ex: <https://example.com/> .
        ex:s ex:p "selected" .
        """,
    )

    profile = load_profile_config(tmp_path / "worai.toml").get("alpha")
    protocol = ProfileImportProtocol(
        context=_context(),
        profile=profile,
        root_dir=tmp_path,
    )
    protocol._ensure_templates_loaded()

    assert protocol._template_graph is not None
    assert (
        URIRef("https://example.com/s"),
        URIRef("https://example.com/p"),
        Literal("selected"),
    ) in protocol._template_graph
    assert (
        URIRef("https://example.com/s"),
        URIRef("https://example.com/p"),
        Literal("base"),
    ) not in protocol._template_graph


def test_exports_override_prefers_selected_key(tmp_path: Path) -> None:
    _write(
        tmp_path / "worai.toml",
        """
        [profiles._base]

        [profiles.alpha]
        """,
    )
    _write(
        tmp_path / "profiles" / "_base" / "templates" / "exports.toml",
        """
        shared = "base"
        base_only = "b"
        """,
    )
    _write(
        tmp_path / "profiles" / "alpha" / "templates" / "exports.toml",
        """
        shared = "selected"
        selected_only = "s"
        """,
    )

    profile = load_profile_config(tmp_path / "worai.toml").get("alpha")
    protocol = ProfileImportProtocol(
        context=_context(),
        profile=profile,
        root_dir=tmp_path,
    )
    protocol._ensure_templates_loaded()

    assert protocol._template_exports == {
        "shared": "selected",
        "base_only": "b",
        "selected_only": "s",
    }


def test_mappings_inheritance_and_selected_path_override(tmp_path: Path) -> None:
    _write(
        tmp_path / "worai.toml",
        """
        [profiles._base]
        mapping = "default.yarrrml"

        [profiles.alpha]
        """,
    )
    _write(
        tmp_path / "profiles" / "_base" / "mappings" / "default.yarrrml", "mappings: {}"
    )

    profile = load_profile_config(tmp_path / "worai.toml").get("alpha")
    protocol = ProfileImportProtocol(
        context=_context(),
        profile=profile,
        root_dir=tmp_path,
    )
    inherited_path = protocol._resolve_mapping_path("https://example.com/page")
    assert (
        inherited_path
        == tmp_path / "profiles" / "_base" / "mappings" / "default.yarrrml"
    )

    _write(
        tmp_path / "profiles" / "alpha" / "mappings" / "default.yarrrml",
        "mappings: { selected: {} }",
    )
    overridden_path = protocol._resolve_mapping_path("https://example.com/page")
    assert (
        overridden_path
        == tmp_path / "profiles" / "alpha" / "mappings" / "default.yarrrml"
    )


def test_profile_specific_only_projects_keep_existing_behavior(tmp_path: Path) -> None:
    _write(
        tmp_path / "worai.toml",
        """
        [profiles.alpha]
        mapping = "custom.yarrrml"
        """,
    )
    _write(
        tmp_path / "profiles" / "alpha" / "mappings" / "custom.yarrrml",
        "mappings: { profile: {} }",
    )
    _write(
        tmp_path / "profiles" / "alpha" / "templates" / "exports.toml",
        """
        only = "alpha"
        """,
    )

    profile = load_profile_config(tmp_path / "worai.toml").get("alpha")
    protocol = ProfileImportProtocol(
        context=_context(),
        profile=profile,
        root_dir=tmp_path,
    )
    resolved = protocol._resolve_mapping_path("https://example.com/page")
    protocol._ensure_templates_loaded()

    assert profile.mapping == "custom.yarrrml"
    assert resolved == tmp_path / "profiles" / "alpha" / "mappings" / "custom.yarrrml"
    assert protocol._template_exports == {"only": "alpha"}
