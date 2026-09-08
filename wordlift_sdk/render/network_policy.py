"""Mandatory browser network policy for analytics traffic."""

from __future__ import annotations

import re


_BLOCKED_GOOGLE_ANALYTICS_HOST_SUFFIXES = (
    "google-analytics.com",
    "analytics.google.com",
)
_BLOCKED_MEASUREMENT_PATHS = (r"/(?:g|j|mp|r|batch)/collect",)

_HOST_ALTERNATION = "|".join(
    re.escape(host) for host in _BLOCKED_GOOGLE_ANALYTICS_HOST_SUFFIXES
)
_PATH_ALTERNATION = "|".join(_BLOCKED_MEASUREMENT_PATHS)

GOOGLE_ANALYTICS_URL_PATTERN = re.compile(
    r"^https?://(?:[^/?#@]*@)?(?:"
    # the Analytics measurement hosts themselves, whatever the path
    rf"(?:[^./?#:@]+\.)*(?:{_HOST_ALTERNATION})\.?(?::\d+)?(?:[/?#]|$)"
    # or any host, when the path is a GA measurement endpoint
    rf"|[^/?#]+(?:{_PATH_ALTERNATION})(?:[/?#]|$)"
    r")",
    re.IGNORECASE,
)
