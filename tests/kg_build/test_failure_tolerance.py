from __future__ import annotations

import pytest

from wordlift_sdk.kg_build.failure_tolerance import FailureTolerance


def test_default_tolerates_no_failures() -> None:
    tolerance = FailureTolerance()
    assert tolerance.tolerates(0, 100) is True
    assert tolerance.tolerates(1, 9106) is False


def test_absolute_count_tolerance() -> None:
    tolerance = FailureTolerance(max_failed_urls=2)
    assert tolerance.tolerates(2, 10) is True
    assert tolerance.tolerates(3, 10) is False


@pytest.mark.parametrize(
    ("ratio", "failures", "url_count", "expected"),
    [
        (0.005, 45, 9106, True),
        (0.005, 46, 9106, False),
        (0.29, 29, 100, True),  # no float floor error: 0.29 * 100 < 29
        (0.5, 1, 0, False),
    ],
)
def test_ratio_tolerance(
    ratio: float, failures: int, url_count: int, expected: bool
) -> None:
    tolerance = FailureTolerance(max_failed_urls_ratio=ratio)
    assert tolerance.tolerates(failures, url_count) is expected


def test_either_limit_tolerates() -> None:
    tolerance = FailureTolerance(max_failed_urls=5, max_failed_urls_ratio=0.01)
    assert tolerance.tolerates(5, 10) is True  # count wins on small runs
    assert tolerance.tolerates(50, 5000) is True  # ratio wins on large runs
    assert tolerance.tolerates(51, 5000) is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_failed_urls": -1},
        {"max_failed_urls_ratio": -0.1},
        {"max_failed_urls_ratio": 1.5},
    ],
)
def test_rejects_out_of_range_values(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        FailureTolerance(**kwargs)


def test_describe() -> None:
    assert (
        FailureTolerance(max_failed_urls=2, max_failed_urls_ratio=0.005).describe()
        == "MAX_FAILED_URLS=2, MAX_FAILED_URLS_RATIO=0.005"
    )
