"""Canonical URL selection by title clusters using GSC impressions."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import pandas as pd
from google.auth.credentials import Credentials
from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials as UserCredentials

from wordlift_sdk.utils.auto_concurrency import AutoConcurrencyController

WEBMASTERS_READONLY_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
_INTERVAL_PATTERN = re.compile(r"^\s*(\d+)\s*([dwmDWM])\s*$")


@dataclass(frozen=True)
class DateRange:
    """Inclusive GSC date range."""

    start_date: date
    end_date: date


def parse_interval_to_date_range(interval: str, today: date | None = None) -> DateRange:
    """Parse `XX[d|w|m]` and return an inclusive date range ending yesterday."""

    match = _INTERVAL_PATTERN.match(interval)
    if not match:
        raise ValueError("interval must match XX[d|w|m], for example: 28d, 4w, 1m.")

    count = int(match.group(1))
    unit = match.group(2).lower()

    if unit == "d":
        total_days = count
    elif unit == "w":
        total_days = count * 7
    else:
        # Month support is explicit and intentionally simple (30-day month).
        total_days = count * 30

    current_day = today or date.today()
    end_date = current_day - timedelta(days=1)
    start_date = end_date - timedelta(days=total_days - 1)
    return DateRange(start_date=start_date, end_date=end_date)


def load_service_account_credentials(
    service_account_file: str | Path, *, scopes: list[str] | None = None
) -> Credentials:
    """Load GSC credentials from a Google service-account JSON file."""

    return service_account.Credentials.from_service_account_file(
        str(service_account_file), scopes=scopes or [WEBMASTERS_READONLY_SCOPE]
    )


def load_authorized_user_credentials(
    authorized_user_file: str | Path, *, scopes: list[str] | None = None
) -> Credentials:
    """Load GSC credentials from an OAuth authorized-user token JSON file."""

    return UserCredentials.from_authorized_user_file(
        str(authorized_user_file), scopes=scopes or [WEBMASTERS_READONLY_SCOPE]
    )


def create_canonical_csv_from_gsc_impressions(
    *,
    input_csv: str | Path,
    output_csv: str | Path,
    site_url: str,
    credentials: Credentials | None = None,
    service_account_file: str | Path | None = None,
    authorized_user_file: str | Path | None = None,
    interval: str = "28d",
    url_regex: str | None = None,
    concurrency: str = "auto",
    auto_min_concurrency: int = 2,
    auto_max_concurrency: int = 12,
    auto_initial_concurrency: int = 4,
    request_timeout_sec: float = 30.0,
) -> pd.DataFrame:
    """Build `url,title,canonical` output from input CSV and GSC impressions.

    Cluster rule is exact-title matching. Canonical is selected by highest
    impressions in the interval; ties are broken by first appearance in input.
    """

    creds = _resolve_credentials(
        credentials=credentials,
        service_account_file=service_account_file,
        authorized_user_file=authorized_user_file,
    )
    date_range = parse_interval_to_date_range(interval)
    source_df = _read_and_filter_input(input_csv=input_csv, url_regex=url_regex)

    if source_df.empty:
        result = source_df.assign(canonical=pd.Series(dtype="string"))[
            ["url", "title", "canonical"]
        ]
        result.to_csv(output_csv, index=False)
        return result

    if not creds.valid and creds.expired and creds.refresh_token:
        # Refresh once before concurrent calls to avoid refresh races.
        creds.refresh(Request())

    impressions = _load_impressions_for_urls(
        urls=source_df["url"].tolist(),
        site_url=site_url,
        date_range=date_range,
        credentials=creds,
        max_concurrent_requests=concurrency,
        auto_min_concurrency=auto_min_concurrency,
        auto_max_concurrency=auto_max_concurrency,
        auto_initial_concurrency=auto_initial_concurrency,
        request_timeout_sec=request_timeout_sec,
    )

    result = _assign_canonical_by_title(source_df=source_df, impressions=impressions)
    result.to_csv(output_csv, index=False)
    return result


def _resolve_credentials(
    *,
    credentials: Credentials | None,
    service_account_file: str | Path | None,
    authorized_user_file: str | Path | None,
) -> Credentials:
    """Resolve exactly one credential source."""

    provided = [
        credentials is not None,
        service_account_file is not None,
        authorized_user_file is not None,
    ]
    if sum(provided) != 1:
        raise ValueError(
            "Provide exactly one credential source: credentials, "
            "service_account_file, or authorized_user_file."
        )

    if credentials is not None:
        return credentials
    if service_account_file is not None:
        return load_service_account_credentials(service_account_file)
    return load_authorized_user_credentials(authorized_user_file)  # type: ignore[arg-type]


def _read_and_filter_input(
    input_csv: str | Path, url_regex: str | None
) -> pd.DataFrame:
    """Read required columns and apply optional URL regex filtering."""

    df = pd.read_csv(input_csv)
    required_columns = {"url", "title"}
    missing = required_columns - set(df.columns)
    if missing:
        missing_cols = ", ".join(sorted(missing))
        raise ValueError(f"Input CSV missing required columns: {missing_cols}")

    out = df[["url", "title"]].copy()
    out["url"] = out["url"].astype(str)
    out["title"] = out["title"].astype(str)

    if url_regex:
        pattern = re.compile(url_regex)
        out = out[out["url"].map(lambda value: bool(pattern.search(value)))]

    # Keep deterministic tie-breaking based on original input order.
    out = out.reset_index(drop=True)
    out["input_order"] = out.index
    return out


def _load_impressions_for_urls(
    *,
    urls: list[str],
    site_url: str,
    date_range: DateRange,
    credentials: Credentials,
    max_concurrent_requests: str,
    auto_min_concurrency: int,
    auto_max_concurrency: int,
    auto_initial_concurrency: int,
    request_timeout_sec: float,
) -> dict[str, float]:
    """Fetch impressions for URLs with fixed or adaptive concurrency."""

    concurrency = AutoConcurrencyController.from_value(
        max_concurrent_requests,
        min_auto_workers=auto_min_concurrency,
        max_auto_workers=auto_max_concurrency,
        initial_auto_workers=auto_initial_concurrency,
    )
    pending = list(urls)
    impressions: dict[str, float] = {}

    while pending:
        batch = pending[: concurrency.current_workers]
        pending = pending[concurrency.current_workers :]

        status_codes: list[int | None] = []
        with ThreadPoolExecutor(max_workers=concurrency.current_workers) as executor:
            futures = {
                executor.submit(
                    _query_url_impressions,
                    site_url,
                    url,
                    date_range,
                    credentials,
                    request_timeout_sec,
                ): url
                for url in batch
            }
            for future in as_completed(futures):
                url = futures[future]
                value, status_code = future.result()
                impressions[url] = value
                status_codes.append(status_code)

        concurrency.update_from_status_codes(status_codes)

    return impressions


def _query_url_impressions(
    site_url: str,
    url: str,
    date_range: DateRange,
    credentials: Credentials,
    request_timeout_sec: float,
) -> tuple[float, int | None]:
    """Query one URL from Search Console Search Analytics API."""

    encoded_site_url = quote(site_url, safe="")
    endpoint = (
        "https://searchconsole.googleapis.com/webmasters/v3/sites/"
        f"{encoded_site_url}/searchAnalytics/query"
    )
    payload = {
        "startDate": date_range.start_date.isoformat(),
        "endDate": date_range.end_date.isoformat(),
        "dimensions": ["page"],
        "dimensionFilterGroups": [
            {
                "filters": [
                    {
                        "dimension": "page",
                        "operator": "equals",
                        "expression": url,
                    }
                ]
            }
        ],
        "rowLimit": 1,
    }

    with AuthorizedSession(credentials) as session:
        try:
            response = session.post(
                endpoint,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=request_timeout_sec,
            )
        except Exception:
            # Treat transport-level failures as 0 impressions with "error" status.
            return 0.0, None

    if response.status_code != 200:
        # Explicitly preserve the status for adaptive concurrency.
        return 0.0, response.status_code

    body = response.json()
    rows = body.get("rows", [])
    if not rows:
        return 0.0, response.status_code

    impressions = rows[0].get("impressions", 0.0)
    try:
        return float(impressions), response.status_code
    except (TypeError, ValueError):
        return 0.0, response.status_code


def _assign_canonical_by_title(
    *, source_df: pd.DataFrame, impressions: dict[str, float]
) -> pd.DataFrame:
    """Assign canonical URL for each title cluster."""

    df = source_df.copy()
    df["impressions"] = df["url"].map(lambda value: float(impressions.get(value, 0.0)))

    # Sort so the first row per title is the canonical:
    # - highest impressions first
    # - original input order as deterministic tie-breaker
    ranked = df.sort_values(
        by=["title", "impressions", "input_order"],
        ascending=[True, False, True],
        kind="mergesort",
    )
    canonical_by_title = ranked.drop_duplicates(
        subset=["title"], keep="first"
    ).set_index("title")["url"]

    out = df.copy()
    out["canonical"] = out["title"].map(canonical_by_title)
    return out[["url", "title", "canonical"]]
