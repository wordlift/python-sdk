# Render

Rendering utilities for fetching HTML with Playwright and converting it to XHTML for structured data generation.

## Core classes

### HtmlRenderer
Renders a URL using `Browser` and converts HTML to XHTML with `HtmlConverter`.

- `render(options: RenderOptions) -> RenderedPage`

### Browser
Thin wrapper around Playwright that opens a page and returns the page, response, elapsed time, and resource list.

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
