# GSC Canonical Selection Spec

## Purpose

Define the SDK contract used by clients (for example Worai CLI) to generate
`url,title,canonical` outputs by clustering rows by title and electing the URL
with highest Google Search Console impressions.

## Public API

File: `wordlift_sdk/google_search_console/canonical_selection.py`

- `create_canonical_csv_from_gsc_impressions(...) -> pandas.DataFrame`
- `parse_interval_to_date_range(interval) -> DateRange`
- `load_service_account_credentials(service_account_file, scopes=None) -> Credentials`
- `load_authorized_user_credentials(authorized_user_file, scopes=None) -> Credentials`

## Input Contract

- Required CSV columns: `url`, `title`.
- Optional filter: `url_regex` (regex applied to `url` before GSC calls).
- Interval format: `XX[d|w|m]` (examples: `28d`, `4w`, `2m`).
- Concurrency format: `concurrency = N | auto` where:
  - `N` is a positive integer string.
  - `auto` enables adaptive ramp-up/ramp-down.

## Output Contract

- Output CSV columns: `url,title,canonical`.
- Canonical election:
  - cluster key: exact `title`
  - score: GSC impressions in interval
  - tie-break: first row order in input CSV
  - missing GSC data: `0` impressions

## Authentication Contract

Exactly one credential source must be supplied to
`create_canonical_csv_from_gsc_impressions`:

- `credentials`: pre-built Google credentials object
- `service_account_file`: service-account JSON path
- `authorized_user_file`: OAuth authorized-user token JSON path

Client responsibility:

1. If user-auth is required, client opens OAuth authorization UX.
2. Client exchanges code/token and persists authorized-user credentials.
3. Client passes `credentials` or `authorized_user_file` to SDK method.

SDK scope for GSC reads:

- `https://www.googleapis.com/auth/webmasters.readonly`

## Concurrency Behavior

Adaptive mode uses shared controller:

- `wordlift_sdk.utils.auto_concurrency.AutoConcurrencyController`

Policy:

- Decrease workers by 1 on status buckets: `throttle` (`429`), `server_error`
  (`5xx`), `error` (transport/unknown).
- Increase workers by 1 only when batch buckets are all `ok`.
- Clamp within configured bounds.

## Migration Note for Client Implementers

- Canonical-selection API uses `concurrency` as the single public concurrency
  input (`N|auto`).
- Do not send deprecated alias fields such as `max_concurrent_requests`.

## Implementation References

- `wordlift_sdk/google_search_console/canonical_selection.py`
- `wordlift_sdk/utils/auto_concurrency.py`
- `tests/test_google_search_console_canonical_selection.py`
- `tests/utils/test_auto_concurrency.py`
