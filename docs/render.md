# Render

Rendering utilities for fetching HTML with Playwright and converting it to XHTML for structured data generation.

## Core classes

### HtmlRenderer
Renders a URL using `Browser` and converts HTML to XHTML with `HtmlConverter`.

- `render(options: RenderOptions) -> RenderedPage`

### Browser
Thin wrapper around Playwright that opens a page and returns the page, response, elapsed time, and resource list.

Each browser context blocks service workers and installs a mandatory context-wide
route that aborts traffic to Google Analytics measurement endpoints: any path on
`*.google-analytics.com` and `*.analytics.google.com`, plus the measurement paths
`/g/collect`, `/j/collect`, `/mp/collect`, `/r/collect` and
`/batch/collect` on any host. The path rule is needed
because the Google tag sends the same GA4 payload (same `tid=G-...`) to other
hosts, notably `www.google.com/g/collect`, when the measurement hosts are
unreachable. Google Tag Manager and advertising conversion endpoints
(`/ccm/collect`) remain available. Blocked URLs and payloads are not
logged or added to the response-resource list. Customer-specific first-party or
server-side tagging gateways that route measurement through their own path are
outside this policy.
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
