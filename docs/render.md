# Render

Rendering utilities for fetching HTML with Playwright and converting it to XHTML for structured data generation.

## Core classes

### HtmlRenderer
Renders a URL using `Browser` and converts HTML to XHTML with `HtmlConverter`.

- `render(options: RenderOptions) -> RenderedPage`

### Browser
Thin wrapper around Playwright that opens a page and returns the page, response, elapsed time, and resource list.

Each browser context blocks service workers and installs a mandatory context-wide
route that aborts Google Analytics measurement traffic. Two host groups are
treated differently:

- `*.google-analytics.com` and `*.analytics.google.com` exist only to collect,
  so every path on them is blocked.
- `*.google.com` and `*.stats.g.doubleclick.net` also serve traffic that must
  stay reachable, so only the measurement paths are blocked there:
  `/g/collect`, `/j/collect`, `/mp/collect`, `/r/collect` and `/batch/collect`.
  The path rule is needed because the Google tag sends the same GA4 payload to
  `www.google.com/g/collect` when the measurement hosts are unreachable.

Hosts are enumerated deliberately. A path rule applied to any host cannot be
bounded, because third-party endpoint names are unpredictable, so third-party
hosts are out of scope whatever they call their paths. Google Tag Manager and
advertising conversion endpoints (`/ccm/collect`, `/rmkt/collect/<id>/`) remain
available. Blocked URLs and payloads are not logged or added to the
response-resource list. Customer-specific first-party or server-side tagging
gateways that route measurement through their own path are outside this policy.
Disabling service workers intentionally trades PWA offline caching and
background-sync fidelity for complete context-route coverage.

### RenderOptions
Configuration for rendering:
- `url`, `headless`, `timeout_ms`, `wait_until`, `locale`, `user_agent`, `viewport_width`, `viewport_height`, `ignore_https_errors`

### RenderedPage
Container for:
- `html`, `xhtml`, `status_code`, `resources`

### XhtmlCleaner
Cleans and truncates XHTML for prompt usage.

### CleanupOptions
Controls XHTML cleanup:
- `max_xhtml_chars`, `max_text_node_chars`

## Convenience functions

- `render_html(options: RenderOptions) -> RenderedPage`
- `clean_xhtml(xhtml: str, options: CleanupOptions) -> str`

## Example

```python
from wordlift_sdk.render import RenderOptions, render_html

options = RenderOptions(
    url="https://example.com",
    headless=True,
    timeout_ms=30000,
    wait_until="networkidle",
)

page = render_html(options)
print(page.status_code)
```
