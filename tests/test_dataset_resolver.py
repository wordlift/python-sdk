from __future__ import annotations

import sys
import types

import pytest

if "wordlift_client" not in sys.modules:
    try:
        import wordlift_client  # noqa: F401
    except Exception:
        _fake_client = types.ModuleType("wordlift_client")

        class _ApiClient:  # noqa: D401 - simple stub
            pass

        class _Configuration:
            def __init__(self, *args, **kwargs) -> None:
                self.api_key = {}

        class _AgentApi:
            def __init__(self, *args, **kwargs) -> None:
                pass

        class _AccountApi:
            def __init__(self, *args, **kwargs) -> None:
                pass

            async def get_me(self):
                return types.SimpleNamespace(dataset_uri="urn:dataset")

        _fake_client.ApiClient = _ApiClient
        _fake_client.Configuration = _Configuration
        _fake_client.AgentApi = _AgentApi
        _fake_client.AccountApi = _AccountApi
        sys.modules.setdefault("wordlift_client", _fake_client)

        _models_module = types.ModuleType("wordlift_client.models")
        _ask_module = types.ModuleType("wordlift_client.models.ask_request")

        class _AskRequest:
            def __init__(self, *args, **kwargs) -> None:
                pass

        _ask_module.AskRequest = _AskRequest
        sys.modules.setdefault("wordlift_client.models", _models_module)
        sys.modules.setdefault("wordlift_client.models.ask_request", _ask_module)

_pyshacl = types.ModuleType("pyshacl")


def _stub_validate(*_args, **_kwargs):
    return None, None, None


_pyshacl.validate = _stub_validate
sys.modules.setdefault("pyshacl", _pyshacl)

from wordlift_sdk.structured_data.dataset_resolver import DatasetResolver  # noqa: E402


def test_dataset_resolver_get_dataset_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeAccount:
        dataset_uri = "urn:dataset"

    class _FakeAccountApi:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def get_me(self):
            return _FakeAccount()

    sys.modules.setdefault("wordlift_client", types.ModuleType("wordlift_client"))
    sys.modules["wordlift_client"].AccountApi = _FakeAccountApi

    resolver = DatasetResolver()

    monkeypatch.setattr(
        "wordlift_sdk.structured_data.dataset_resolver.get_dataset_uri",
        lambda api_key, base_url=None, ssl_ca_cert=None: "urn:dataset",
    )

    assert resolver.get_dataset_uri("k") == "urn:dataset"
