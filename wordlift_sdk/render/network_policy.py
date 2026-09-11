"""Mandatory browser network policy for analytics traffic."""

from __future__ import annotations

import re

# ============================================================================
# Shared vocabulary: which hosts and paths are in scope. Both the Chromium
# glob patterns and the Playwright regex below are rendered from these same
# tuples -- keep them in sync when either mechanism's rules change.
# ============================================================================

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


# ============================================================================
# Chromium: `Network.setBlockedURLs` glob patterns.
#
# The dialect is `base::MatchPattern`: `*` matches any run of characters,
# everything else is literal, and the pattern must match the whole URL. There
# are no character classes and no anchoring finer than "the whole string" --
# so, unlike the regex below, a wildcard here can't be bounded to "stop at the
# next `/`". That is what lets `*.`/`*@` accidentally swallow more than a
# subdomain or credentials (see docs/render.md), and why there's no path
# terminator on the mixed-host patterns.
# ============================================================================

# GA4 is served from regional subdomains as well as the apex -- we observed
# region1.google-analytics.com -- and one spelling does not match the other.
# `*@` covers credentials on the apex; `*.` already absorbs them on a subdomain.
_HOST_FORMS = ("", "*.", "*@")

_PORT_FORMS = ("", ":*")


def _authorities(hosts: tuple[str, ...]) -> list[str]:
    # e.g. for "google-analytics.com": https://google-analytics.com,
    # https://google-analytics.com:*, https://*.google-analytics.com,
    # https://*.google-analytics.com:*, https://*@google-analytics.com,
    # https://*@google-analytics.com:*
    return [
        f"https://{form}{host}{port}"
        for host in hosts
        for form in _HOST_FORMS
        for port in _PORT_FORMS
    ]


def build_blocked_url_patterns() -> list[str]:
    # e.g. "https://*.google-analytics.com/**" and
    # "https://*.google.com:*/g/collect*"
    return [
        f"{authority}/**" for authority in _authorities(_MEASUREMENT_ONLY_HOSTS)
    ] + [
        f"{authority}{path}*"
        for authority in _authorities(_MIXED_HOSTS)
        for path in _MEASUREMENT_PATHS
    ]


# ============================================================================
# Other engines: Playwright route regex.
#
# This is the precise version of the same rule: unlike the glob above, it can
# bound the path (`_TERMINATOR`) and see userinfo, ports and `http://`. Only
# Chromium is launched today, so this path is not currently reached.
# ============================================================================

_SUBDOMAINS = r"(?:[^./?#:@]+\.)*"
_HOST_TAIL = r"\.?(?::\d+)?"
_TERMINATOR = r"(?:[/?#]|$)"

_ONLY_HOSTS_RE = "|".join(re.escape(host) for host in _MEASUREMENT_ONLY_HOSTS)
_MIXED_HOSTS_RE = "|".join(re.escape(host) for host in _MIXED_HOSTS)
_PATHS_RE = "|".join(re.escape(path) for path in _MEASUREMENT_PATHS)

# Matches, e.g.: https://region1.google-analytics.com/g/collect and
# https://user:pass@google.com:8443/g/collect?x=1
# Does not match: https://www.google.com/g/collectXYZ (terminator blocks it)
GOOGLE_ANALYTICS_URL_PATTERN = re.compile(
    r"^https?://(?:[^/?#@]*@)?(?:"
    rf"{_SUBDOMAINS}(?:{_ONLY_HOSTS_RE}){_HOST_TAIL}{_TERMINATOR}"
    rf"|{_SUBDOMAINS}(?:{_MIXED_HOSTS_RE}){_HOST_TAIL}(?:{_PATHS_RE}){_TERMINATOR}"
    r")",
    re.IGNORECASE,
)
