from __future__ import annotations

import asyncio
import importlib
from datetime import datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from wordlift_sdk.google_search_console.create_google_search_console_data_import import (
    create_google_search_console_data_import,
    import_url_analytics_factory,
)
from wordlift_sdk.google_search_console.raise_error_if_account_analytics_not_configured import (
    raise_error_if_account_analytics_not_configured,
)

gsc_import_mod = importlib.import_module(
    "wordlift_sdk.google_search_console.create_google_search_console_data_import"
)


@pytest.mark.asyncio
async def test_create_google_search_console_data_import_only_imports_stale_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now()
    source_df = pd.DataFrame(
        [
            {
                "url": "https://example.com/stale-1",
                "top_query_date_created": now - timedelta(days=30),
            },
            {
                "url": "https://example.com/fresh",
                "top_query_date_created": now - timedelta(days=1),
            },
            {"url": "https://example.com/stale-2", "top_query_date_created": pd.NaT},
        ]
    )

    async def _fake_entities_df(key, url_list):
        return source_df

    monkeypatch.setattr(
        gsc_import_mod, "create_entities_with_top_query_dataframe", _fake_entities_df
    )

    called_urls: list[str] = []

    async def _import_row(row):
        called_urls.append(row["url"])

    async def _fake_import_factory(configuration):
        return _import_row

    monkeypatch.setattr(
        gsc_import_mod, "import_url_analytics_factory", _fake_import_factory
    )
    monkeypatch.setattr(
        gsc_import_mod, "create_delayed", lambda callback, _concurrency: callback
    )

    async def _fake_gather(*aws, total):
        return await asyncio.gather(*aws)

    monkeypatch.setattr(gsc_import_mod.tqdm, "gather", _fake_gather)

    await create_google_search_console_data_import(
        configuration=SimpleNamespace(),
        key="k",
        url_list=[
            "https://example.com/stale-1",
            "https://example.com/fresh",
            "https://example.com/stale-2",
        ],
    )

    assert sorted(called_urls) == [
        "https://example.com/stale-1",
        "https://example.com/stale-2",
    ]


@pytest.mark.asyncio
async def test_create_google_search_console_data_import_skips_when_no_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now()
    source_df = pd.DataFrame(
        [
            {
                "url": "https://example.com/fresh",
                "top_query_date_created": now - timedelta(days=1),
            }
        ]
    )

    async def _fake_entities_df(key, url_list):
        return source_df

    monkeypatch.setattr(
        gsc_import_mod, "create_entities_with_top_query_dataframe", _fake_entities_df
    )

    calls: dict[str, int] = {"gather": 0}

    async def _import_row(_row):
        raise AssertionError("should not import fresh row")

    async def _fake_import_factory(configuration):
        return _import_row

    monkeypatch.setattr(
        gsc_import_mod, "import_url_analytics_factory", _fake_import_factory
    )
    monkeypatch.setattr(
        gsc_import_mod, "create_delayed", lambda callback, _concurrency: callback
    )

    async def _fake_gather(*aws, total):
        calls["gather"] += 1
        return []

    monkeypatch.setattr(gsc_import_mod.tqdm, "gather", _fake_gather)

    await create_google_search_console_data_import(
        configuration=SimpleNamespace(),
        key="k",
        url_list=["https://example.com/fresh"],
    )
    assert calls["gather"] == 0


@pytest.mark.asyncio
async def test_import_url_analytics_factory_calls_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, object]] = []

    class _ApiClient:
        def __init__(self, configuration):
            self.configuration = configuration

        async def __aenter__(self):
            events.append(("enter", self.configuration))
            return self

        async def __aexit__(self, exc_type, exc, tb):
            events.append(("exit", None))
            return False

    class _AnalyticsImportsApi:
        def __init__(self, api_client):
            self.api_client = api_client

        async def create_analytics_import(self, request):
            events.append(("import", request.urls))

    monkeypatch.setattr(gsc_import_mod.wordlift_client, "ApiClient", _ApiClient)
    monkeypatch.setattr(
        gsc_import_mod.wordlift_client, "AnalyticsImportsApi", _AnalyticsImportsApi
    )

    callback = await import_url_analytics_factory(configuration="cfg")
    await callback(pd.Series({"url": "https://example.com/a"}))
    assert ("enter", "cfg") in events
    assert ("import", ["https://example.com/a"]) in events
    assert ("exit", None) in events


@pytest.mark.asyncio
async def test_raise_error_if_account_analytics_not_configured() -> None:
    with pytest.raises(ValueError, match="not connected to Google Search Console"):
        await raise_error_if_account_analytics_not_configured(
            SimpleNamespace(
                google_search_console_site_url=None,
                dataset_uri="https://data.example.org",
                country_code="US",
            )
        )

    with pytest.raises(ValueError, match="country code not configured"):
        await raise_error_if_account_analytics_not_configured(
            SimpleNamespace(
                google_search_console_site_url="sc-domain:example.com",
                dataset_uri="https://data.example.org",
                country_code=None,
            )
        )

    with pytest.raises(ValueError, match="Country code ZZ is invalid"):
        await raise_error_if_account_analytics_not_configured(
            SimpleNamespace(
                google_search_console_site_url="sc-domain:example.com",
                dataset_uri="https://data.example.org",
                country_code="zz",
            )
        )

    assert (
        await raise_error_if_account_analytics_not_configured(
            SimpleNamespace(
                google_search_console_site_url="sc-domain:example.com",
                dataset_uri="https://data.example.org",
                country_code="us",
            )
        )
        is True
    )
