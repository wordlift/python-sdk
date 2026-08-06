"""Mandatory browser network policy for analytics traffic."""

from __future__ import annotations

import re


_BLOCKED_GOOGLE_ANALYTICS_HOST_SUFFIXES = (
    "google-analytics.com",
    "analytics.google.com",
)

GOOGLE_ANALYTICS_URL_PATTERN = re.compile(
    r"^https?://(?:[^/?#@]*@)?(?:[^./?#:@]+\.)*(?:"
    + "|".join(re.escape(host) for host in _BLOCKED_GOOGLE_ANALYTICS_HOST_SUFFIXES)
    + r")\.?(?::\d+)?(?:[/?#]|$)",
    re.IGNORECASE,
)
