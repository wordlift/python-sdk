from __future__ import annotations

from types import SimpleNamespace

import pytest

import wordlift_sdk.utils.ssl_ca_bundle as ssl_ca_bundle


def _make_ca_file(tmp_path):
    path = tmp_path / "ca.pem"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ca")
    return path


def test_resolve_ssl_ca_cert_prefers_override(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    override = _make_ca_file(tmp_path)
    monkeypatch.setattr(ssl_ca_bundle.os, "name", "posix")
    monkeypatch.setattr(
        ssl_ca_bundle.os, "uname", lambda: SimpleNamespace(sysname="Darwin")
    )

    assert ssl_ca_bundle.resolve_ssl_ca_cert(str(override)) == str(override)


def test_resolve_ssl_ca_cert_prefers_system_on_macos(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    system_ca = _make_ca_file(tmp_path)
    certifi_ca = _make_ca_file(tmp_path / "certifi")

    monkeypatch.setattr(ssl_ca_bundle.os, "name", "posix")
    monkeypatch.setattr(
        ssl_ca_bundle.os, "uname", lambda: SimpleNamespace(sysname="Darwin")
    )
    monkeypatch.setattr(
        ssl_ca_bundle.ssl,
        "get_default_verify_paths",
        lambda: SimpleNamespace(cafile=str(system_ca), openssl_cafile=None),
    )
    monkeypatch.setattr(
        ssl_ca_bundle, "certifi", SimpleNamespace(where=lambda: str(certifi_ca))
    )

    assert ssl_ca_bundle.resolve_ssl_ca_cert(None) == str(system_ca)


def test_resolve_ssl_ca_cert_falls_back_to_certifi_on_macos(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    certifi_ca = _make_ca_file(tmp_path)

    monkeypatch.setattr(ssl_ca_bundle.os, "name", "posix")
    monkeypatch.setattr(
        ssl_ca_bundle.os, "uname", lambda: SimpleNamespace(sysname="Darwin")
    )
    monkeypatch.setattr(
        ssl_ca_bundle.ssl,
        "get_default_verify_paths",
        lambda: SimpleNamespace(cafile=None, openssl_cafile=None),
    )
    monkeypatch.setattr(
        ssl_ca_bundle, "certifi", SimpleNamespace(where=lambda: str(certifi_ca))
    )

    assert ssl_ca_bundle.resolve_ssl_ca_cert(None) == str(certifi_ca)


def test_resolve_ssl_ca_cert_uses_system_on_non_macos(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    system_ca = _make_ca_file(tmp_path)

    monkeypatch.setattr(ssl_ca_bundle.os, "name", "posix")
    monkeypatch.setattr(
        ssl_ca_bundle.os, "uname", lambda: SimpleNamespace(sysname="Linux")
    )
    monkeypatch.setattr(
        ssl_ca_bundle.ssl,
        "get_default_verify_paths",
        lambda: SimpleNamespace(cafile=str(system_ca), openssl_cafile=None),
    )

    assert ssl_ca_bundle.resolve_ssl_ca_cert(None) == str(system_ca)
