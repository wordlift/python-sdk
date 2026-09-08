"""Mandatory browser network policy for analytics traffic."""

from __future__ import annotations

import re


# Hosts that exist only to collect Analytics measurement: block every path.
_MEASUREMENT_ONLY_HOST_SUFFIXES = (
    "google-analytics.com",
    "analytics.google.com",
)

# Google hosts that also serve traffic which must stay reachable (advertising
# conversions, remarketing, search). Only the measurement paths below are
# blocked on these:
#   google.com               observed sending GA4 page_view to /g/collect
#   stats.g.doubleclick.net  documented GA4/Signals endpoint, not observed here
_MIXED_GOOGLE_HOST_SUFFIXES = (
    "google.com",
    "stats.g.doubleclick.net",
)

# The prefix before `collect` denotes the request type: `g` (GA4 browser),
# `j` (Universal Analytics JS), `mp` (Measurement Protocol), `r` (raw) and
# `batch` (batched). Advertising paths on the mixed hosts -- `/ccm/collect`,
# `/rmkt/collect/<id>/` -- are deliberately absent so they stay reachable.
#
# Hosts are enumerated rather than matched openly: a path rule applied to any
# host cannot be bounded, since third-party endpoint names are unpredictable.
_MEASUREMENT_PATHS = r"/(?:g|j|mp|r|batch)/collect"

_SUBDOMAINS = r"(?:[^./?#:@]+\.)*"
_HOST_TAIL = r"\.?(?::\d+)?"
_TERMINATOR = r"(?:[/?#]|$)"

_ONLY = "|".join(re.escape(host) for host in _MEASUREMENT_ONLY_HOST_SUFFIXES)
_MIXED = "|".join(re.escape(host) for host in _MIXED_GOOGLE_HOST_SUFFIXES)

GOOGLE_ANALYTICS_URL_PATTERN = re.compile(
    r"^https?://(?:[^/?#@]*@)?(?:"
    rf"{_SUBDOMAINS}(?:{_ONLY}){_HOST_TAIL}{_TERMINATOR}"
    rf"|{_SUBDOMAINS}(?:{_MIXED}){_HOST_TAIL}{_MEASUREMENT_PATHS}{_TERMINATOR}"
    r")",
    re.IGNORECASE,
)
