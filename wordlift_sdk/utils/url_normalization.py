"""URL normalization shared by IRI hashing and redirect detection."""

from __future__ import annotations

from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

_DEFAULT_PORTS = {"http": 80, "https": 443}
_PATH_SAFE = "/:@!$&'()*+,;=-._~"


def normalize_url(value: str) -> str:
    """Return ``value`` with a sorted query string and no fragment.

    Scheme, host and path are kept as they are, so IRI hashes stay stable. A
    URL that cannot be parsed is returned unchanged.
    """
    try:
        split = urlsplit(value)
        query = urlencode(sorted(parse_qsl(split.query, keep_blank_values=True)))
        return urlunsplit((split.scheme, split.netloc, split.path, query, ""))
    except Exception:
        return value


def is_same_url(left: str, right: str) -> bool:
    """Tell whether two URLs address the same page.

    On top of :func:`normalize_url`, scheme and host case, default ports,
    percent-encoding of the path, and an empty path versus ``/`` are ignored.
    """
    return _comparable(left) == _comparable(right)


def _comparable(value: str) -> str:
    normalized = normalize_url(value)
    try:
        split = urlsplit(normalized)
        scheme = split.scheme.lower()
        host = (split.hostname or "").lower()
        port = split.port
    except ValueError:
        return normalized
    if not host:
        return normalized
    netloc = host if port in (None, _DEFAULT_PORTS.get(scheme)) else f"{host}:{port}"
    path = quote(unquote(split.path), safe=_PATH_SAFE) or "/"
    return urlunsplit((scheme, netloc, path, split.query, ""))
