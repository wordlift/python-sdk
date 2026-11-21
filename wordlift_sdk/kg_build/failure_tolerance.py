"""How many failed URLs a cloud graph sync run tolerates before it fails.

A large sync (thousands of pages) should not turn red because one page could
not be fetched. The run fails only when the failed URLs exceed both an
absolute count (``MAX_FAILED_URLS``) and a share of the run's URLs
(``MAX_FAILED_URLS_RATIO``). Both default to 0: any failure fails the run.
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_FAILED_URLS_KEY = "MAX_FAILED_URLS"
MAX_FAILED_URLS_RATIO_KEY = "MAX_FAILED_URLS_RATIO"


@dataclass(frozen=True)
class FailureTolerance:
    max_failed_urls: int = 0
    max_failed_urls_ratio: float = 0.0

    def __post_init__(self) -> None:
        if self.max_failed_urls < 0:
            raise ValueError(
                f"{MAX_FAILED_URLS_KEY} must be >= 0, got {self.max_failed_urls}."
            )
        if not 0.0 <= self.max_failed_urls_ratio <= 1.0:
            raise ValueError(
                f"{MAX_FAILED_URLS_RATIO_KEY} must be between 0 and 1, "
                f"got {self.max_failed_urls_ratio}."
            )

    def tolerates(self, failed_url_count: int, url_count: int) -> bool:
        if failed_url_count <= self.max_failed_urls:
            return True
        return (
            url_count > 0 and failed_url_count / url_count <= self.max_failed_urls_ratio
        )

    def describe(self) -> str:
        return (
            f"{MAX_FAILED_URLS_KEY}={self.max_failed_urls}, "
            f"{MAX_FAILED_URLS_RATIO_KEY}={self.max_failed_urls_ratio:g}"
        )


__all__ = [
    "FailureTolerance",
    "MAX_FAILED_URLS_KEY",
    "MAX_FAILED_URLS_RATIO_KEY",
]
