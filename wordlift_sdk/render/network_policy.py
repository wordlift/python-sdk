"""Mandatory browser network policy for analytics traffic."""

from __future__ import annotations

import re

# Hosts observed serving Google Analytics measurement endpoints. These exist
# only to collect measurement, so every path on them is blocked.
_MEASUREMENT_ONLY_HOSTS = (
    "google-analytics.com",
    "analytics.google.com",
)

# `google.com` and `stats.g.doubleclick.net` also serve advertising traffic,
# which the paths below deliberately exclude.
_MIXED_HOSTS = (
    "google.com",
    "stats.g.doubleclick.net",
)

# The prefix before `collect` denotes the request type: `g` (GA4 browser),
# `j` (Universal Analytics JS), `mp` (Measurement Protocol), `r` (raw) and
# `batch` (batched). Advertising paths (`/ccm/collect`, `/rmkt/collect/<id>/`)
# are absent so they stay reachable.
_MEASUREMENT_PATHS = (
    "/batch/collect",
    "/g/collect",
    "/j/collect",
    "/mp/collect",
    "/r/collect",
)

# GA4 is served from regional subdomains as well as the apex -- we observed
# region1.google-analytics.com -- and one spelling does not match the other.
# `*@` covers credentials on the apex; `*.` already absorbs them on a subdomain.
_HOST_FORMS = ("", "*.", "*@")

_PORT_FORMS = ("", ":*")

_SUBDOMAINS = r"(?:[^./?#:@]+\.)*"
_HOST_TAIL = r"\.?(?::\d+)?"
_TERMINATOR = r"(?:[/?#]|$)"

_ONLY_HOSTS_RE = "|".join(re.escape(host) for host in _MEASUREMENT_ONLY_HOSTS)
_MIXED_HOSTS_RE = "|".join(re.escape(host) for host in _MIXED_HOSTS)
_PATHS_RE = "|".join(re.escape(path) for path in _MEASUREMENT_PATHS)

# Playwright matches a route with a regex; Chromium matches a glob anywhere in
# the URL. The same hosts and paths are rendered for both, and only the regex can
# bound the path or see userinfo, ports and `http://`.
GOOGLE_ANALYTICS_URL_PATTERN = re.compile(
    r"^https?://(?:[^/?#@]*@)?(?:"
    rf"{_SUBDOMAINS}(?:{_ONLY_HOSTS_RE}){_HOST_TAIL}{_TERMINATOR}"
    rf"|{_SUBDOMAINS}(?:{_MIXED_HOSTS_RE}){_HOST_TAIL}(?:{_PATHS_RE}){_TERMINATOR}"
    r")",
    re.IGNORECASE,
)


def _authorities(hosts: tuple[str, ...]) -> list[str]:
    return [
        f"https://{form}{host}{port}"
        for host in hosts
        for form in _HOST_FORMS
        for port in _PORT_FORMS
    ]


def build_blocked_url_patterns() -> list[str]:
    return [
        f"{authority}/**" for authority in _authorities(_MEASUREMENT_ONLY_HOSTS)
    ] + [
        f"{authority}{path}*"
        for authority in _authorities(_MIXED_HOSTS)
        for path in _MEASUREMENT_PATHS
    ]
