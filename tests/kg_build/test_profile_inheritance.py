from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
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


def test_base_root_exports_available_to_selected_templates(tmp_path: Path) -> None:
    _write(
        tmp_path / "worai.toml",
        """
        [profiles._base]

        [profiles.alpha]
        """,
    )
    _write(
        tmp_path / "profiles" / "_base" / "exports.toml.j2",
        """
        organization_iri = "{{ dataset_uri }}/organizations/base-org"
        """,
    )
    _write(
        tmp_path / "profiles" / "alpha" / "templates" / "entity.ttl.j2",
        """
        @prefix ex: <https://example.com/> .
        ex:s ex:p <{{ exports.organization_iri }}> .
        """,
    )

    profile = load_profile_config(tmp_path / "worai.toml").get("alpha")
    protocol = ProfileImportProtocol(
        context=_context(),
        profile=profile,
        root_dir=tmp_path,
    )
    protocol._ensure_templates_loaded()

    assert protocol._template_exports is not None
    assert protocol._template_exports["organization_iri"].endswith(
        "/organizations/base-org"
    )
    assert protocol._template_graph is not None
    assert (
        URIRef("https://example.com/s"),
        URIRef("https://example.com/p"),
        URIRef("https://data.example.com/dataset/organizations/base-org"),
    ) in protocol._template_graph


def test_base_templates_with_empty_selected_exports_still_use_base(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "worai.toml",
        """
        [profiles._base]

        [profiles.alpha]
        """,
    )
    _write(
        tmp_path / "profiles" / "_base" / "exports.toml",
        """
        organization_iri = "https://example.com/base-org"
        """,
    )
    _write(
        tmp_path / "profiles" / "_base" / "templates" / "entity.ttl.j2",
        """
        @prefix ex: <https://example.com/> .
        ex:s ex:p <{{ exports.organization_iri }}> .
        """,
    )
    _write(
        tmp_path / "profiles" / "alpha" / "exports.toml",
        """
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
        "organization_iri": "https://example.com/base-org"
    }
    assert protocol._template_graph is not None
    assert (
        URIRef("https://example.com/s"),
        URIRef("https://example.com/p"),
        URIRef("https://example.com/base-org"),
    ) in protocol._template_graph


def test_selected_root_exports_override_base_key(tmp_path: Path) -> None:
    _write(
        tmp_path / "worai.toml",
        """
        [profiles._base]

        [profiles.alpha]
        """,
    )
    _write(
        tmp_path / "profiles" / "_base" / "exports.toml",
        """
        organization_iri = "https://example.com/base-org"
        """,
    )
    _write(
        tmp_path / "profiles" / "alpha" / "exports.toml",
        """
        organization_iri = "https://example.com/selected-org"
        """,
    )
    _write(
        tmp_path / "profiles" / "_base" / "templates" / "entity.ttl.j2",
        """
        @prefix ex: <https://example.com/> .
        ex:s ex:p <{{ exports.organization_iri }}> .
        """,
    )

    profile = load_profile_config(tmp_path / "worai.toml").get("alpha")
    protocol = ProfileImportProtocol(
        context=_context(),
        profile=profile,
        root_dir=tmp_path,
    )
    protocol._ensure_templates_loaded()

    assert protocol._template_exports is not None
    assert (
        protocol._template_exports["organization_iri"]
        == "https://example.com/selected-org"
    )
    assert protocol._template_graph is not None
    assert (
        URIRef("https://example.com/s"),
        URIRef("https://example.com/p"),
        URIRef("https://example.com/selected-org"),
    ) in protocol._template_graph


def test_missing_export_key_reports_lookup_diagnostics(tmp_path: Path) -> None:
    _write(
        tmp_path / "worai.toml",
        """
        [profiles._base]

        [profiles.alpha]
        """,
    )
    _write(
        tmp_path / "profiles" / "_base" / "templates" / "entity.ttl.j2",
        """
        @prefix ex: <https://example.com/> .
        ex:s ex:p <{{ exports.organization_iri }}> .
        """,
    )

    profile = load_profile_config(tmp_path / "worai.toml").get("alpha")
    protocol = ProfileImportProtocol(
        context=_context(),
        profile=profile,
        root_dir=tmp_path,
    )

    with pytest.raises(RuntimeError) as exc_info:
        protocol._ensure_templates_loaded()

    message = str(exc_info.value)
    assert "profile 'alpha'" in message
    assert "Searched exports files:" in message
    assert "profiles/_base/exports.toml" in message
    assert "Loaded exports files: []" in message
    assert "_base exports loaded: False" in message
