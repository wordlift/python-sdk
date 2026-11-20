"""URL normalization shared by IRI hashing and redirect detection."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def normalize_url(value: str) -> str:
    """Return ``value`` with a sorted query string and no fragment.

    Scheme, host and path are kept as they are. A URL that cannot be parsed is
    returned unchanged.
    """
    try:
        split = urlsplit(value)
        query = urlencode(sorted(parse_qsl(split.query, keep_blank_values=True)))
        return urlunsplit((split.scheme, split.netloc, split.path, query, ""))
    except Exception:
        return value


def is_same_url(left: str, right: str) -> bool:
    """Tell whether two URLs address the same page once normalized.

    An empty path and ``/`` are treated as the same path.
    """
    return _comparable(left) == _comparable(right)


def _comparable(value: str) -> str:
    normalized = normalize_url(value)
    split = urlsplit(normalized)
    if split.netloc and not split.path:
        return urlunsplit((split.scheme, split.netloc, "/", split.query, ""))
    return normalized
