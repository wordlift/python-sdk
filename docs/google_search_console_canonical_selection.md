# Google Search Console Canonical Selection

Use `wordlift_sdk.google_search_console.create_canonical_csv_from_gsc_impressions`
to produce canonical URL assignments from an input CSV (`url,title`) using Search
Console impressions.

## API

File: `wordlift_sdk/google_search_console/canonical_selection.py`

- `create_canonical_csv_from_gsc_impressions(...) -> pandas.DataFrame`
- `parse_interval_to_date_range(interval) -> DateRange`
- `load_service_account_credentials(service_account_file, scopes=None) -> Credentials`
- `load_authorized_user_credentials(authorized_user_file, scopes=None) -> Credentials`

## Input / Output

- Input CSV required columns: `url`, `title`.
- Optional URL filtering: `url_regex`.
- Output CSV columns: `url`, `title`, `canonical`.

## Canonical Election Rules

- Cluster key: exact `title`.
- Score: Search Console impressions for each URL in the requested interval.
- Tie-break: first URL occurrence in input CSV.
- Missing rows in GSC response: impressions default to `0`.

## Interval Format

- `XX[d|w|m]` where:
- `d` = days
- `w` = weeks (7-day units)
- `m` = months (30-day units)

Example values: `28d`, `4w`, `2m`.

## Authentication

Exactly one credential source must be provided:

- `credentials`: already-built Google credentials object (recommended when host
  client performs user OAuth flow).
- `service_account_file`: service-account JSON file.
- `authorized_user_file`: OAuth authorized-user token JSON file.

This allows host applications (for example Worai client CLI) to authenticate the
end user with their own Google account and pass credentials into the SDK method.

## Concurrency

- `concurrency` accepts an integer string or `"auto"`.
- `"auto"` uses adaptive ramp-up/ramp-down policy via shared
  `wordlift_sdk.utils.auto_concurrency.AutoConcurrencyController`.
- Advanced tuning is available with `auto_min_concurrency`,
  `auto_max_concurrency`, and `auto_initial_concurrency` when needed.
