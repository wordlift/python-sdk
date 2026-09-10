# Render

Rendering utilities for fetching HTML with Playwright and converting it to XHTML for structured data generation.

## Core classes

### HtmlRenderer
Renders a URL using `Browser` and converts HTML to XHTML with `HtmlConverter`.

- `render(options: RenderOptions) -> RenderedPage`

### Browser
Thin wrapper around Playwright that opens a page and returns the page, response, elapsed time, and resource list.

Each browser context blocks service workers, and every page blocks Google
Analytics measurement traffic as it is created.

The policy is defined once as hosts and measurement paths:

- every path on `google-analytics.com` and `analytics.google.com`, which exist
  only to collect measurement
- the measurement paths `/batch/collect`, `/g/collect`, `/j/collect`,
  `/mp/collect` and `/r/collect` on `google.com` and `stats.g.doubleclick.net`,
  which also serve traffic that must stay reachable

Each host is listed with and without a subdomain wildcard.

`google.com` is on the list because the Google tag sends the same GA4 payload to
`www.google.com/g/collect` when the measurement hosts are unreachable.

Hosts are enumerated deliberately. A path rule applied to any host cannot be
bounded, because third-party endpoint names are unpredictable, so third-party
hosts are out of scope whatever they call their paths. Google Tag Manager and
advertising conversion endpoints (`/ccm/collect`, `/rmkt/collect/<id>/`) remain
available.

On Chromium it is rendered as URL globs and applied with
`Network.setBlockedURLs`, which blocks inside the browser's own network stack.
Other engines fall back to a Playwright route over the equivalent regex. That
fallback is weaker: a route decision is a round trip out of the browser,
Playwright stops answering as soon as the page is closed, and the browser then
sends any request it has not been told to block. The regex is the more precise
of the two -- it bounds the path and covers credentials, ports and `http://`,
which the glob syntax cannot express. Only Chromium is launched today, so the
route is not currently reached.

Blocked URLs and payloads are not logged or added to the
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
