from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from wordlift_sdk.google_search_console.canonical_selection import (
    DateRange,
    create_canonical_csv_from_gsc_impressions,
    parse_interval_to_date_range,
)


@dataclass
class _FakeCredentials:
    valid: bool = True
    expired: bool = False
    refresh_token: str | None = None
    refresh_calls: int = 0

    def refresh(self, _request) -> None:
        self.refresh_calls += 1
        self.valid = True
        self.expired = False


def _write_input_csv(path: Path) -> None:
    pd.DataFrame(
        [
            {"url": "https://example.com/a1", "title": "A"},
            {"url": "https://example.com/a2", "title": "A"},
            {"url": "https://example.com/b1", "title": "B"},
        ]
    ).to_csv(path, index=False)


def test_parse_interval_to_date_range() -> None:
    parsed = parse_interval_to_date_range("28d", today=date(2026, 2, 26))
    assert parsed.start_date.isoformat() == "2026-01-29"
    assert parsed.end_date.isoformat() == "2026-02-25"

    parsed_week = parse_interval_to_date_range("4w", today=date(2026, 2, 26))
    assert parsed_week.start_date.isoformat() == "2026-01-29"

    parsed_month = parse_interval_to_date_range("1m", today=date(2026, 2, 26))
    assert parsed_month.start_date.isoformat() == "2026-01-27"

    with pytest.raises(ValueError, match="XX\\[d\\|w\\|m\\]"):
        parse_interval_to_date_range("bad")


def test_loaders_and_resolve_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, object] = {}

    def _fake_sa_loader(path: str, scopes: list[str]):
        called["sa"] = (path, scopes)
        return "sa-creds"

    def _fake_user_loader(path: str, scopes: list[str]):
        called["user"] = (path, scopes)
        return "user-creds"

    monkeypatch.setattr(
        "wordlift_sdk.google_search_console.canonical_selection.service_account.Credentials.from_service_account_file",
        _fake_sa_loader,
    )
    monkeypatch.setattr(
        "wordlift_sdk.google_search_console.canonical_selection.UserCredentials.from_authorized_user_file",
        _fake_user_loader,
    )

    from wordlift_sdk.google_search_console.canonical_selection import (
        WEBMASTERS_READONLY_SCOPE,
        _resolve_credentials,
        load_authorized_user_credentials,
        load_service_account_credentials,
    )

    assert load_service_account_credentials("/tmp/sa.json") == "sa-creds"
    assert called["sa"] == ("/tmp/sa.json", [WEBMASTERS_READONLY_SCOPE])

    assert load_authorized_user_credentials("/tmp/user.json") == "user-creds"
    assert called["user"] == ("/tmp/user.json", [WEBMASTERS_READONLY_SCOPE])

    assert (
        _resolve_credentials(
            credentials=None,
            service_account_file="/tmp/sa.json",
            authorized_user_file=None,
        )
        == "sa-creds"
    )
    assert (
        _resolve_credentials(
            credentials=None,
            service_account_file=None,
            authorized_user_file="/tmp/user.json",
        )
        == "user-creds"
    )


def test_create_canonical_csv_filters_regex_and_tie_breaks_input_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "output.csv"
    _write_input_csv(input_csv)

    captured: dict[str, object] = {}

    def _fake_impressions_loader(**kwargs):
        captured.update(kwargs)
        return {
            "https://example.com/a1": 10.0,
            "https://example.com/a2": 10.0,  # tie with a1, keep first in input
            # b1 missing -> 0 fallback
        }

    monkeypatch.setattr(
        "wordlift_sdk.google_search_console.canonical_selection._load_impressions_for_urls",
        _fake_impressions_loader,
    )

    result = create_canonical_csv_from_gsc_impressions(
        input_csv=input_csv,
        output_csv=output_csv,
        site_url="sc-domain:example.com",
        credentials=_FakeCredentials(),
        interval="28d",
        url_regex=r"/a|/b1$",
        concurrency="auto",
    )

    assert output_csv.exists()
    written = pd.read_csv(output_csv)
    assert list(written.columns) == ["url", "title", "canonical"]
    assert written.equals(result)

    # A cluster should elect a1 due to tie-break on input order.
    a_rows = result[result["title"] == "A"]
    assert set(a_rows["canonical"]) == {"https://example.com/a1"}

    # B cluster has one URL and missing impressions -> still canonical to itself.
    b_rows = result[result["title"] == "B"]
    assert set(b_rows["canonical"]) == {"https://example.com/b1"}

    # Regex still included all three rows with this pattern.
    assert captured["urls"] == [
        "https://example.com/a1",
        "https://example.com/a2",
        "https://example.com/b1",
    ]


def test_create_canonical_csv_validates_single_credential_source(
    tmp_path: Path,
) -> None:
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "output.csv"
    _write_input_csv(input_csv)

    with pytest.raises(ValueError, match="exactly one credential source"):
        create_canonical_csv_from_gsc_impressions(
            input_csv=input_csv,
            output_csv=output_csv,
            site_url="sc-domain:example.com",
            credentials=_FakeCredentials(),
            service_account_file="/tmp/sa.json",
        )


def test_create_canonical_csv_refreshes_expired_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "output.csv"
    _write_input_csv(input_csv)

    monkeypatch.setattr(
        "wordlift_sdk.google_search_console.canonical_selection._load_impressions_for_urls",
        lambda **kwargs: {url: 1.0 for url in kwargs["urls"]},
    )

    creds = _FakeCredentials(valid=False, expired=True, refresh_token="rt")
    create_canonical_csv_from_gsc_impressions(
        input_csv=input_csv,
        output_csv=output_csv,
        site_url="sc-domain:example.com",
        credentials=creds,
    )
    assert creds.refresh_calls == 1


def test_create_canonical_csv_uses_empty_result_when_regex_filters_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "output.csv"
    _write_input_csv(input_csv)

    # No API calls expected when filter removes every row.
    monkeypatch.setattr(
        "wordlift_sdk.google_search_console.canonical_selection._load_impressions_for_urls",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not be called")),
    )

    result = create_canonical_csv_from_gsc_impressions(
        input_csv=input_csv,
        output_csv=output_csv,
        site_url="sc-domain:example.com",
        credentials=_FakeCredentials(),
        interval="28d",
        url_regex=r"nomatch",
    )

    assert list(result.columns) == ["url", "title", "canonical"]
    assert result.empty
    assert pd.read_csv(output_csv).empty


def test_read_and_filter_input_validates_required_columns(tmp_path: Path) -> None:
    bad_csv = tmp_path / "bad.csv"
    pd.DataFrame([{"url": "https://example.com"}]).to_csv(bad_csv, index=False)

    from wordlift_sdk.google_search_console.canonical_selection import (
        _read_and_filter_input,
    )

    with pytest.raises(ValueError, match="missing required columns: title"):
        _read_and_filter_input(bad_csv, None)


def test_query_url_impressions_response_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        def __init__(self, status_code: int, body: dict):
            self.status_code = status_code
            self._body = body

        def json(self):
            return self._body

    class _Session:
        def __init__(self, response=None, error: Exception | None = None):
            self._response = response
            self._error = error

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, endpoint, data, headers, timeout):
            assert "sc-domain%3Aexample.com" in endpoint
            assert headers["Content-Type"] == "application/json"
            assert timeout == 1.0
            if self._error:
                raise self._error
            return self._response

    from wordlift_sdk.google_search_console.canonical_selection import (
        _query_url_impressions,
    )

    monkeypatch.setattr(
        "wordlift_sdk.google_search_console.canonical_selection.AuthorizedSession",
        lambda creds: _Session(response=_Resp(200, {"rows": [{"impressions": 12}]})),
    )
    ok_value, ok_status = _query_url_impressions(
        "sc-domain:example.com",
        "https://example.com/a",
        DateRange(start_date=date(2026, 1, 1), end_date=date(2026, 1, 28)),
        credentials=SimpleNamespace(),
        request_timeout_sec=1.0,
    )
    assert (ok_value, ok_status) == (12.0, 200)

    monkeypatch.setattr(
        "wordlift_sdk.google_search_console.canonical_selection.AuthorizedSession",
        lambda creds: _Session(response=_Resp(503, {})),
    )
    assert _query_url_impressions(
        "sc-domain:example.com",
        "https://example.com/a",
        DateRange(start_date=date(2026, 1, 1), end_date=date(2026, 1, 28)),
        credentials=SimpleNamespace(),
        request_timeout_sec=1.0,
    ) == (0.0, 503)

    monkeypatch.setattr(
        "wordlift_sdk.google_search_console.canonical_selection.AuthorizedSession",
        lambda creds: _Session(response=_Resp(200, {"rows": []})),
    )
    assert _query_url_impressions(
        "sc-domain:example.com",
        "https://example.com/a",
        DateRange(start_date=date(2026, 1, 1), end_date=date(2026, 1, 28)),
        credentials=SimpleNamespace(),
        request_timeout_sec=1.0,
    ) == (0.0, 200)

    monkeypatch.setattr(
        "wordlift_sdk.google_search_console.canonical_selection.AuthorizedSession",
        lambda creds: _Session(response=_Resp(200, {"rows": [{"impressions": "x"}]})),
    )
    assert _query_url_impressions(
        "sc-domain:example.com",
        "https://example.com/a",
        DateRange(start_date=date(2026, 1, 1), end_date=date(2026, 1, 28)),
        credentials=SimpleNamespace(),
        request_timeout_sec=1.0,
    ) == (0.0, 200)

    monkeypatch.setattr(
        "wordlift_sdk.google_search_console.canonical_selection.AuthorizedSession",
        lambda creds: _Session(error=RuntimeError("boom")),
    )
    assert _query_url_impressions(
        "sc-domain:example.com",
        "https://example.com/a",
        DateRange(start_date=date(2026, 1, 1), end_date=date(2026, 1, 28)),
        credentials=SimpleNamespace(),
        request_timeout_sec=1.0,
    ) == (0.0, None)


def test_query_batch_respects_auto_controller_transitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # This test exercises adaptive update wiring in batch loader.
    calls: list[str] = []

    def _fake_query(site_url, url, date_range, credentials, request_timeout_sec):
        calls.append(url)
        if url.endswith("1"):
            return 1.0, 200
        if url.endswith("2"):
            return 2.0, 429
        return 3.0, 200

    monkeypatch.setattr(
        "wordlift_sdk.google_search_console.canonical_selection._query_url_impressions",
        _fake_query,
    )

    from wordlift_sdk.google_search_console.canonical_selection import (
        _load_impressions_for_urls,
    )

    out = _load_impressions_for_urls(
        urls=["u1", "u2", "u3"],
        site_url="sc-domain:example.com",
        date_range=DateRange(start_date=date(2026, 1, 1), end_date=date(2026, 1, 28)),
        credentials=_FakeCredentials(),
        max_concurrent_requests="auto",
        auto_min_concurrency=1,
        auto_max_concurrency=3,
        auto_initial_concurrency=2,
        request_timeout_sec=1.0,
    )
    assert out == {"u1": 1.0, "u2": 2.0, "u3": 3.0}
    assert sorted(calls) == ["u1", "u2", "u3"]
