from __future__ import annotations

import pytest

from wordlift_sdk.render.network_policy import (
    GOOGLE_ANALYTICS_URL_PATTERN,
)


@pytest.mark.parametrize(
    "url",
    [
        # Measurement-only hosts: every path is blocked.
        "https://www.google-analytics.com/g/collect",
        "https://www.google-analytics.com/collect?v=1",
        "https://www.google-analytics.com/batch",
        "https://user:pass@www.google-analytics.com/g/collect",
        "https://region1.google-analytics.com/mp/collect",
        "https://ANALYTICS.GOOGLE.COM./g/collect",
        # Mixed Google hosts: only the measurement paths.
        "https://www.google.com/g/collect?v=2&tid=G-39JJ9JH4VW",
        "https://www.google.com/j/collect",
        "https://www.google.com/mp/collect",
        "https://www.google.com/r/collect",
        "https://www.google.com/batch/collect",
        "https://stats.g.doubleclick.net/g/collect?tid=G-1",
    ],
)
def test_measurement_endpoints_are_blocked(url: str) -> None:
    assert GOOGLE_ANALYTICS_URL_PATTERN.search(url)


@pytest.mark.parametrize(
    "url",
    [
        # Advertising and remarketing on the mixed hosts stay reachable.
        "https://www.google.com/ccm/collect?en=page_view",
        "https://www.google.com/rmkt/collect/1072206699/",
        "https://pagead2.googlesyndication.com/ccm/collect?en=page_view",
        "https://ad.doubleclick.net/ccm/s/collect",
        "https://pagead2.googlesyndication.com/pagead/gen_204",
        # Google Tag Manager stays reachable: some sites inject tags through it
        # that the rendered markup depends on.
        "https://www.googletagmanager.com/gtm.js?id=GTM-123",
        "https://www.googletagmanager.com/gtag/js?id=G-123",
        "https://tagmanager.google.com/",
        # Third-party hosts are out of scope, whatever they call their paths.
        "https://acme.com/g/collect",
        "https://acme.com/batch/collect",
        "https://sgtm.example.com/g/collect",
        "https://px.ads.linkedin.com/collect?pid=1",
        "https://r.clarity.ms/collect",
        "https://example.com/assets/analytics.js",
        # Hosts that merely look like the real ones.
        "https://notgoogle.com/g/collect",
        "https://evilgoogle-analytics.com/collect",
        "https://google.com.evil.org/g/collect",
        "https://google-analytics.com.example.org/collect",
        "https://user@google-analytics.com.example.org/collect",
        "https://google.com/",
        "https://" + "a." * 64 + "example.com/",
        "not a url",
        "https://[invalid",
    ],
)
def test_unrelated_and_malformed_urls_are_allowed(url: str) -> None:
    assert not GOOGLE_ANALYTICS_URL_PATTERN.search(url)
