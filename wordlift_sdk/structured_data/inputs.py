"""Input resolution helpers for structured data workflows."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse


def is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"}


def urls_from_sitemap(source: str) -> list[str]:
    try:
        import advertools as adv
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(
            "advertools is required. Install with: pip install advertools"
        ) from exc
    df = adv.sitemap_to_df(source)
    if df is None or df.empty:
        return []
    for column in ("loc", "url"):
        if column in df.columns:
            values = df[column].dropna().astype(str).tolist()
            return [value for value in values if value]
    return df.iloc[:, 0].dropna().astype(str).tolist()


def resolve_input_urls(value: str) -> list[str]:
    path = Path(value)
    if path.exists():
        urls = urls_from_sitemap(str(path))
        if not urls:
            raise RuntimeError("No URLs found in sitemap file.")
        return urls
    if is_url(value):
        try:
            urls = urls_from_sitemap(value)
            if urls:
                return urls
        except Exception:
            pass
        return [value]
    raise RuntimeError("INPUT must be a sitemap URL/path or a page URL.")


def filter_urls(urls: list[str], regex: str, max_pages: int | None) -> list[str]:
    import re

    pattern = re.compile(regex)
    urls = [url for url in urls if pattern.search(url)]
    if not urls:
        raise RuntimeError("No URLs matched the provided regex.")
    if max_pages is not None:
        urls = urls[:max_pages]
    return urls
