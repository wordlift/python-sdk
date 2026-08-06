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
    ],
)
def test_google_analytics_urls_are_blocked(url: str) -> None:
    assert GOOGLE_ANALYTICS_URL_PATTERN.search(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/assets/analytics.js",
        "https://evilgoogle-analytics.com/collect",
        "https://google-analytics.com.example.org/collect",
        "https://user@google-analytics.com.example.org/collect",
        "https://www.googletagmanager.com/gtm.js?id=GTM-123",
        "https://www.googletagmanager.com/gtag/js?id=G-123",
        "https://tagmanager.google.com/",
        "https://stats.g.doubleclick.net/g/collect",
        "https://pagead2.googlesyndication.com/pagead/gen_204",
        "https://example.com/g/collect",
        "https://google.com/",
        "https://" + "a." * 64 + "example.com/",
        "not a url",
        "https://[invalid",
    ],
)
def test_unrelated_and_malformed_urls_are_allowed(url: str) -> None:
    assert not GOOGLE_ANALYTICS_URL_PATTERN.search(url)
