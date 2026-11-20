from wordlift_sdk.utils.url_normalization import is_same_url, normalize_url


def test_normalize_url_sorts_query_and_drops_fragment() -> None:
    assert normalize_url("https://a.com/p?b=2&a=1#f") == "https://a.com/p?a=1&b=2"


def test_normalize_url_returns_unparsable_value_unchanged() -> None:
    assert normalize_url("http://[::1") == "http://[::1"


def test_is_same_url() -> None:
    assert is_same_url("https://a.com", "https://a.com/")
    assert is_same_url("https://a.com/p?b=2&a=1", "https://a.com/p?a=1&b=2#x")
    assert not is_same_url("https://a.com/p", "https://a.com/q")
    assert not is_same_url("http://a.com/p", "https://a.com/p")
