"""Shared adaptive-concurrency helpers.

This module centralizes "auto" worker ramp-up/ramp-down behavior so multiple
features can reuse one policy implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass
class AutoConcurrencyController:
    """Controls fixed or adaptive worker counts.

    The controller accepts either an explicit integer worker count or "auto".
    In auto mode, worker count increases when all results are healthy and
    decreases when throttling/server failures/errors are detected.
    """

    auto: bool
    min_workers: int
    max_workers: int
    current_workers: int

    @classmethod
    def from_value(
        cls,
        value: str,
        *,
        min_auto_workers: int = 2,
        max_auto_workers: int = 12,
        initial_auto_workers: int = 4,
    ) -> "AutoConcurrencyController":
        """Build a controller from a string value.

        Accepted values are:
        - "auto": adaptive mode
        - positive integer as text: fixed worker count
        """

        if value.strip().lower() == "auto":
            current = min(max_auto_workers, max(min_auto_workers, initial_auto_workers))
            return cls(
                auto=True,
                min_workers=min_auto_workers,
                max_workers=max_auto_workers,
                current_workers=current,
            )

        try:
            workers = int(value)
        except ValueError as exc:
            raise RuntimeError("Concurrency must be an integer or 'auto'.") from exc

        if workers <= 0:
            raise RuntimeError("Concurrency must be greater than 0.")

        return cls(
            auto=False,
            min_workers=workers,
            max_workers=workers,
            current_workers=workers,
        )

    @staticmethod
    def status_bucket(status_code: int | None) -> str:
        """Normalize an HTTP-like status code into a control bucket."""

        if status_code is None:
            return "error"
        if status_code == 429:
            return "throttle"
        if 500 <= status_code < 600:
            return "server_error"
        if 200 <= status_code < 400:
            return "ok"
        return "client_error"

    def update_from_status_codes(self, status_codes: Iterable[int | None]) -> int:
        """Update auto mode from status codes and return the new worker count."""

        buckets = {self.status_bucket(code) for code in status_codes}
        return self.update_from_buckets(buckets)

    def update_from_buckets(self, buckets: set[str]) -> int:
        """Update auto mode from normalized status buckets.

        Rules in auto mode:
        - decrease by 1 on throttle/server_error/error buckets
        - increase by 1 only when all buckets are "ok"
        """

        if not self.auto:
            return self.current_workers

        if buckets & {"throttle", "server_error", "error"}:
            self.current_workers = max(self.min_workers, self.current_workers - 1)
            return self.current_workers

        if buckets == {"ok"}:
            self.current_workers = min(self.max_workers, self.current_workers + 1)

        return self.current_workers
