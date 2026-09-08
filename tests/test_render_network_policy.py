from __future__ import annotations

import pytest

from wordlift_sdk.render.network_policy import (
    GOOGLE_ANALYTICS_URL_PATTERN,
)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.google-analytics.com/g/collect",
        "https://user:pass@www.google-analytics.com/g/collect",
        "https://region1.google-analytics.com/mp/collect",
        "https://ANALYTICS.GOOGLE.COM./g/collect",
        # Measurement endpoints on other hosts: the Google tag sends the same
        # GA4 payload here when the measurement hosts are unavailable.
        "https://www.google.com/g/collect?v=2&tid=G-39JJ9JH4VW",
        # Other measurement request types: r (raw), batch, j (UA JS), mp.
        "https://www.google.com/r/collect?v=2",
        "https://www.google.com/batch/collect",
        "https://www.google-analytics.com/j/collect",
        "https://stats.g.doubleclick.net/g/collect?tid=G-1",
        "https://sgtm.example.com/g/collect?v=2&tid=G-1",
        "https://example.com/g/collect",
    ],
)
def test_measurement_endpoints_are_blocked(url: str) -> None:
    assert GOOGLE_ANALYTICS_URL_PATTERN.search(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/assets/analytics.js",
        "https://evilgoogle-analytics.com/collect",
        "https://google-analytics.com.example.org/collect",
        "https://user@google-analytics.com.example.org/collect",
        # Google Tag Manager stays reachable: some sites inject tags through it
        # that the rendered markup depends on.
        "https://www.googletagmanager.com/gtm.js?id=GTM-123",
        "https://www.googletagmanager.com/gtag/js?id=G-123",
        "https://tagmanager.google.com/",
        # Advertising conversion endpoints stay reachable.
        "https://www.google.com/ccm/collect?en=page_view",
        "https://pagead2.googlesyndication.com/ccm/collect?en=page_view",
        "https://ad.doubleclick.net/ccm/s/collect",
        "https://pagead2.googlesyndication.com/pagead/gen_204",
        # The remarketing pixel is advertising, and must not be caught by the
        # `/r/collect` rule -- the segment is `rmkt`, not `r`.
        "https://www.google.com/rmkt/collect/1072206699/",
        # Bare /collect on unrelated vendors is outside this policy.
        "https://px.ads.linkedin.com/collect?pid=1",
        "https://r.clarity.ms/collect",
        # Only measurement paths at the root of the path are matched, so an
        # unrelated page that happens to contain the segment is left alone.
        "https://example.com/foo/g/collect",
        "https://google.com/",
        "https://" + "a." * 64 + "example.com/",
        "not a url",
        "https://[invalid",
    ],
)
def test_unrelated_and_malformed_urls_are_allowed(url: str) -> None:
    assert not GOOGLE_ANALYTICS_URL_PATTERN.search(url)
