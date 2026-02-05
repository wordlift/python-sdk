from __future__ import annotations

import pytest

try:
    import wordlift_client  # noqa: F401
except Exception:
    pytest.skip("wordlift_client not available", allow_module_level=True)

from wordlift_sdk.client.client_configuration_factory import ClientConfigurationFactory


def test_client_configuration_factory_sets_ca_bundle(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ca_path = tmp_path / "ca.pem"
    ca_path.write_text("ca")

    monkeypatch.setattr(
        "wordlift_sdk.client.client_configuration_factory.resolve_ssl_ca_cert",
        lambda _override=None: str(ca_path),
    )

    factory = ClientConfigurationFactory(
        key="test-key", api_url="https://api.wordlift.io", ssl_ca_cert="override"
    )
    configuration = factory.create()

    assert configuration.verify_ssl is True
    assert configuration.ssl_ca_cert == str(ca_path)
