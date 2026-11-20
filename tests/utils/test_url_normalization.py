import pytest

from wordlift_sdk.utils.url_normalization import is_same_url, normalize_url


def test_normalize_url_sorts_query_and_drops_fragment() -> None:
    assert normalize_url("https://a.com/p?b=2&a=1#f") == "https://a.com/p?a=1&b=2"


def test_normalize_url_keeps_host_case_and_path_encoding() -> None:
    assert normalize_url("https://A.com/a%20b") == "https://A.com/a%20b"


def test_normalize_url_returns_unparsable_value_unchanged() -> None:
    assert normalize_url("http://[::1") == "http://[::1"


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("https://a.com", "https://a.com/"),
        ("https://a.com/p?b=2&a=1", "https://a.com/p?a=1&b=2#x"),
        ("https://A.com/p", "https://a.com/p"),
        ("HTTPS://a.com/p", "https://a.com/p"),
        ("https://a.com:443/p", "https://a.com/p"),
        ("http://a.com:80/p", "http://a.com/p"),
        ("https://a.com/a b", "https://a.com/a%20b"),
        ("https://a.com/%c3%a9", "https://a.com/%C3%A9"),
        ("https://a.com/é", "https://a.com/%C3%A9"),
    ],
)
def test_same_page(left: str, right: str) -> None:
    assert is_same_url(left, right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("https://a.com/p", "https://a.com/q"),
        ("http://a.com/p", "https://a.com/p"),
        ("https://a.com:8443/p", "https://a.com/p"),
        ("https://a.com/p/", "https://a.com/p"),
        ("https://a.com/p?a=1", "https://a.com/p?a=2"),
    ],
)
def test_different_page(left: str, right: str) -> None:
    assert not is_same_url(left, right)


def test_relative_and_unparsable_values_compare_as_normalized() -> None:
    assert is_same_url("/p?b=1&a=2", "/p?a=2&b=1")
    assert not is_same_url("http://[::1", "http://[::2")
    assert not is_same_url("http://a.com:bad/p", "http://a.com/p")
