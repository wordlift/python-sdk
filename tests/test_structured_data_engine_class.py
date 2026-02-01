from __future__ import annotations

import sys
import types

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

from wordlift_sdk.structured_data.structured_data_engine import (  # noqa: E402
    StructuredDataEngine,
)


class _StubDataset:
    def __init__(self) -> None:
        self.calls = []

    def get_dataset_uri(self, api_key: str, base_url: str | None = None) -> str:
        self.calls.append((api_key, base_url))
        return "urn:dataset"

    async def get_dataset_uri_async(
        self, api_key: str, base_url: str | None = None
    ) -> str:
        self.calls.append((api_key, base_url))
        return "urn:dataset"


class _StubSchema:
    def __init__(self) -> None:
        self.calls = []

    def shape_specs_for_type(self, type_name: str | None) -> list[str]:
        self.calls.append(type_name)
        return ["dummy"] if type_name else []


class _StubYarrrml:
    def __init__(self) -> None:
        self.calls = []

    def make_reusable_yarrrml(self, yarrml: str, url: str) -> str:
        self.calls.append((yarrml, url))
        return f"# {url}\n{yarrml}"


class _StubAgent:
    def __init__(self) -> None:
        self.calls = []

    def generate_from_agent(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return "mappings: []", {"@type": "Thing"}


def test_structured_data_engine_composition() -> None:
    dataset = _StubDataset()
    schema = _StubSchema()
    yarrrml = _StubYarrrml()
    agent = _StubAgent()

    engine = StructuredDataEngine(
        dataset=dataset,
        schema=schema,
        yarrrml=yarrrml,
        agent=agent,
    )

    assert engine.get_dataset_uri("k") == "urn:dataset"
    assert schema.calls == []

    assert engine.shape_specs_for_type("Thing") == ["dummy"]
    assert schema.calls == ["Thing"]

    assert engine.make_reusable_yarrrml(
        "mappings: []", "https://example.com"
    ).startswith("# https://example.com")
    assert yarrrml.calls

    mappings, jsonld = engine.generate_from_agent(
        "u", "h", "x", "c", "k", "d", "t", None
    )
    assert mappings == "mappings: []"
    assert jsonld["@type"] == "Thing"
