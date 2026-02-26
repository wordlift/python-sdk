from __future__ import annotations

import pytest

from wordlift_sdk.utils.auto_concurrency import AutoConcurrencyController


def test_fixed_concurrency_validation_and_static_behavior() -> None:
    ctrl = AutoConcurrencyController.from_value("3")
    assert ctrl.auto is False
    assert ctrl.current_workers == 3
    assert ctrl.min_workers == 3
    assert ctrl.max_workers == 3

    # Fixed mode must not change workers even on bad buckets.
    assert ctrl.update_from_buckets({"throttle"}) == 3
    assert ctrl.current_workers == 3

    with pytest.raises(RuntimeError, match="integer or 'auto'"):
        AutoConcurrencyController.from_value("nope")

    with pytest.raises(RuntimeError, match="greater than 0"):
        AutoConcurrencyController.from_value("0")


def test_auto_concurrency_ramp_up_and_down() -> None:
    ctrl = AutoConcurrencyController.from_value(
        "auto", min_auto_workers=2, max_auto_workers=5, initial_auto_workers=3
    )
    assert ctrl.auto is True
    assert ctrl.current_workers == 3

    # Fully healthy batch ramps up.
    assert ctrl.update_from_buckets({"ok"}) == 4
    assert ctrl.update_from_buckets({"ok"}) == 5
    # Clamp at max.
    assert ctrl.update_from_buckets({"ok"}) == 5

    # Throttle/error ramps down.
    assert ctrl.update_from_buckets({"ok", "throttle"}) == 4
    assert ctrl.update_from_buckets({"server_error"}) == 3
    assert ctrl.update_from_buckets({"error"}) == 2
    # Clamp at min.
    assert ctrl.update_from_buckets({"error"}) == 2


def test_auto_concurrency_status_bucket_and_status_code_update() -> None:
    assert AutoConcurrencyController.status_bucket(None) == "error"
    assert AutoConcurrencyController.status_bucket(429) == "throttle"
    assert AutoConcurrencyController.status_bucket(503) == "server_error"
    assert AutoConcurrencyController.status_bucket(200) == "ok"
    assert AutoConcurrencyController.status_bucket(404) == "client_error"

    ctrl = AutoConcurrencyController.from_value(
        "auto", min_auto_workers=2, max_auto_workers=5, initial_auto_workers=3
    )
    assert ctrl.update_from_status_codes([200, 204]) == 4
    assert ctrl.update_from_status_codes([429]) == 3
