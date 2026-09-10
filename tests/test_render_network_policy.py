from __future__ import annotations

import pytest

from wordlift_sdk.render.network_policy import (
    GOOGLE_ANALYTICS_URL_PATTERN,
    build_blocked_url_patterns,
)

# Blocked by both strategies.
MEASUREMENT_URLS = [
    "https://www.google-analytics.com/collect?v=1&tid=UA-1",
    "https://www.google-analytics.com/batch",
    "https://www.google-analytics.com/analytics.js",
    "https://www.google-analytics.com/__utm.gif?utmac=UA-1",
    "https://google-analytics.com/g/collect?v=2",
    "https://region1.google-analytics.com/g/collect?v=2&tid=G-XYZ",
    "https://analytics.google.com/mp/collect?api_secret=secret",
    "https://www.google.com/g/collect?v=2&tid=G-XYZ",
    "https://google.com/j/collect?t=pageview",
    "https://stats.g.doubleclick.net/j/collect?t=dc",
    "https://stats.g.doubleclick.net/batch/collect",
    "https://user:pass@google-analytics.com/g/collect?v=2",
    "https://google-analytics.com:8443/g/collect?v=2",
]

# Reachable under both strategies.
REACHABLE_URLS = [
    "https://www.google.com/collections",
    "https://www.google.com/search?q=wordlift",
    "https://www.google.com/ccm/collect?en=conversion",
    "https://stats.g.doubleclick.net/rmkt/collect/12345/",
    "https://www.googletagmanager.com/gtag/js?id=G-XYZ",
    "https://example.com/g/collect?v=2",
]

# The globs are https-only; the regex also covers http.
ROUTE_ONLY_URLS = [
    "http://www.google-analytics.com/g/collect?v=2",
]

# The globs match anywhere in the URL, so they have no path terminator and fire
# on an unrelated host that merely quotes a measurement URL.
CDP_ONLY_URLS = [
    "https://www.google.com/g/collectData123",
    "https://example.com/redirect?to=user@google-analytics.com/g/collect",
]


def _cdp_blocks(url: str) -> bool:
    for pattern in build_blocked_url_patterns():
        position = 0
        for literal in pattern.split("*"):
            if not literal:
                continue
            found = url.find(literal, position)
            if found == -1:
                break
            position = found + len(literal)
        else:
            return True
    return False


def _route_blocks(url: str) -> bool:
    return GOOGLE_ANALYTICS_URL_PATTERN.match(url) is not None


@pytest.mark.parametrize("url", MEASUREMENT_URLS)
def test_measurement_urls_are_blocked_by_both(url: str) -> None:
    assert _cdp_blocks(url)
    assert _route_blocks(url)


@pytest.mark.parametrize("url", REACHABLE_URLS)
def test_other_traffic_stays_reachable_under_both(url: str) -> None:
    assert not _cdp_blocks(url)
    assert not _route_blocks(url)


@pytest.mark.parametrize("url", ROUTE_ONLY_URLS)
def test_route_covers_what_the_globs_cannot(url: str) -> None:
    assert _route_blocks(url)
    assert not _cdp_blocks(url)


@pytest.mark.parametrize("url", CDP_ONLY_URLS)
def test_globs_match_path_prefixes_the_route_terminates(url: str) -> None:
    assert _cdp_blocks(url)
    assert not _route_blocks(url)


def test_advertising_endpoints_stay_reachable() -> None:
    patterns = build_blocked_url_patterns()
    assert not any("/ccm/" in pattern or "/rmkt/" in pattern for pattern in patterns)
    assert not any("googletagmanager.com" in pattern for pattern in patterns)
    assert not GOOGLE_ANALYTICS_URL_PATTERN.match(
        "https://www.google.com/ccm/collect?en=conversion"
    )


def test_the_glob_scheme_is_literal() -> None:
    # A wildcard scheme would swallow the "//" and match look-alike hosts such
    # as https://evilgoogle-analytics.com/g/collect.
    patterns = build_blocked_url_patterns()
    assert patterns
    assert all(pattern.startswith("https://") for pattern in patterns)
    assert not _cdp_blocks("https://evilgoogle-analytics.com/g/collect")
    assert not _route_blocks("https://evilgoogle-analytics.com/g/collect")
