from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from types import SimpleNamespace


from wordlift_sdk.kg_build.report_util import (
    _error_key,
    _format_duration,
    _format_success_rate,
    _format_timestamp,
    _md_cell,
    render_as_csv,
    render_as_markdown,
    write_report,
)


def _failure(url="https://example.com", handler="Handler", message="boom", ts=None):
    return SimpleNamespace(
        timestamp=ts or datetime(2026, 4, 2, 14, 5, 9, tzinfo=timezone.utc),
        url=SimpleNamespace(value=url),
        handler_name=handler,
        message=message,
    )


def _result(url_count=1, failures=None, elapsed_seconds=0.0):
    return SimpleNamespace(
        url_count=url_count,
        failures=failures if failures is not None else [],
        elapsed_seconds=elapsed_seconds,
    )


# --- _md_cell ---


def test_md_cell_escapes_pipe():
    assert _md_cell("hello|world") == "hello\\|world"


def test_md_cell_escapes_newline():
    assert _md_cell("line1\nline2") == "line1 line2"


def test_md_cell_escapes_both():
    assert _md_cell("a|b\nc") == "a\\|b c"


def test_md_cell_plain_text_unchanged():
    assert _md_cell("no special chars") == "no special chars"


# --- _format_timestamp ---


def test_format_timestamp_no_zero_padding_on_day():
    dt = datetime(2026, 4, 2, 14, 5, 9, tzinfo=timezone.utc)
    assert _format_timestamp(dt) == "Apr 2, 14:05:09 UTC"


def test_format_timestamp_midnight_hours_not_corrupted():
    dt = datetime(2026, 4, 1, 0, 5, 9, tzinfo=timezone.utc)
    assert _format_timestamp(dt) == "Apr 1, 00:05:09 UTC"


def test_format_timestamp_double_digit_day():
    dt = datetime(2026, 4, 15, 14, 5, 9, tzinfo=timezone.utc)
    assert _format_timestamp(dt) == "Apr 15, 14:05:09 UTC"


# --- _format_duration ---


def test_format_duration_seconds_only():
    assert _format_duration(45.7) == "45s"


def test_format_duration_minutes_and_seconds():
    assert _format_duration(154.0) == "2m 34s"


def test_format_duration_hours_minutes_seconds():
    assert _format_duration(3922.0) == "1h 5m 22s"


def test_format_duration_zero():
    assert _format_duration(0.0) == "0s"


# --- _format_success_rate ---


def test_format_success_rate_full():
    assert _format_success_rate(10, 10) == "100.0%"


def test_format_success_rate_partial():
    assert _format_success_rate(10, 9) == "90.0%"


def test_format_success_rate_zero_urls():
    assert _format_success_rate(0, 0) == "N/A"


# --- _error_key ---


def test_error_key_strips_url():
    msg = "Ingestion loader returned HTTP error status for https://example.com/page: status_code=403"
    assert "https://" not in _error_key(msg)


def test_error_key_groups_same_http_status():
    msg1 = "HTTP error for https://example.com/a: status_code=403"
    msg2 = "HTTP error for https://example.com/b: status_code=403"
    assert _error_key(msg1) == _error_key(msg2)


def test_error_key_no_url_unchanged():
    msg = "Malformed YARRRML mapping. Validate YAML syntax."
    assert _error_key(msg) == msg


def test_error_key_falls_back_to_message_when_only_url():
    msg = "https://example.com/page"
    assert _error_key(msg) == msg


def test_error_key_truncates_to_prefix_len():
    long_msg = "x" * 200
    assert len(_error_key(long_msg)) <= 80


# --- render_as_markdown ---


def test_render_as_markdown_summary_counts():
    result = _result(url_count=10, failures=[_failure()])
    md = render_as_markdown(result)
    assert "**10**" in md
    assert "**9**" in md
    assert "**1**" in md
    assert "**90.0%**" in md


def test_render_as_markdown_execution_time():
    result = _result(url_count=1, elapsed_seconds=154.0)
    assert "**2m 34s**" in render_as_markdown(result)


def test_render_as_markdown_shows_top_errors_section():
    result = _result(failures=[_failure(message="boom")])
    md = render_as_markdown(result)
    assert "## Top Errors" in md
    assert "boom" in md


def test_render_as_markdown_shows_example_url_and_full_error():
    result = _result(
        failures=[_failure(url="https://ex.com/page", message="Malformed YARRRML")]
    )
    md = render_as_markdown(result)
    assert "https://ex.com/page" in md
    assert "Malformed YARRRML" in md


def test_render_as_markdown_aggregates_same_error():
    result = _result(
        url_count=3,
        failures=[
            _failure(url="https://a.com", message="HTTP error: status_code=403"),
            _failure(url="https://b.com", message="HTTP error: status_code=403"),
            _failure(url="https://c.com", message="other error"),
        ],
    )
    md = render_as_markdown(result)
    assert "| 2 |" in md
    assert "| 1 |" in md


def test_render_as_markdown_groups_http_errors_by_stripping_url():
    result = _result(
        url_count=2,
        failures=[
            _failure(message="HTTP error for https://example.com/a: status_code=403"),
            _failure(message="HTTP error for https://example.com/b: status_code=403"),
        ],
    )
    md = render_as_markdown(result)
    assert "| 2 |" in md


def test_render_as_markdown_no_handler_column():
    result = _result(failures=[_failure(handler="SomeHandler")])
    assert "SomeHandler" not in render_as_markdown(result)


def test_render_as_markdown_escapes_pipe_in_message():
    result = _result(failures=[_failure(message="err|or")])
    assert "err\\|or" in render_as_markdown(result)


def test_render_as_markdown_overflow_note_when_more_than_top_n():
    failures = [_failure(message=f"error type {i}") for i in range(12)]
    md = render_as_markdown(_result(url_count=12, failures=failures))
    assert "2 more error type(s)" in md


def test_render_as_markdown_no_overflow_note_when_within_top_n():
    failures = [_failure(message=f"error type {i}") for i in range(3)]
    md = render_as_markdown(_result(url_count=3, failures=failures))
    assert "more error type" not in md


def test_render_as_markdown_zero_failures_no_top_errors_section():
    result = _result(url_count=5, failures=[])
    md = render_as_markdown(result)
    assert "**0**" in md
    assert "## Top Errors" not in md


def test_render_as_markdown_ends_with_newline():
    assert render_as_markdown(_result()).endswith("\n")


# --- render_as_csv ---


def test_render_as_csv_header():
    rows = list(csv.reader(io.StringIO(render_as_csv([]))))
    assert rows[0] == ["timestamp", "url", "error"]


def test_render_as_csv_no_handler_column():
    rows = list(csv.reader(io.StringIO(render_as_csv([_failure()]))))
    assert len(rows[1]) == 3


def test_render_as_csv_data_row():
    ts = datetime(2026, 4, 2, 14, 5, 9, tzinfo=timezone.utc)
    rows = list(csv.reader(io.StringIO(render_as_csv([_failure(ts=ts)]))))
    assert rows[1] == [ts.isoformat(), "https://example.com", "boom"]


def test_render_as_csv_escapes_comma():
    rows = list(
        csv.reader(io.StringIO(render_as_csv([_failure(message="err, comma")])))
    )
    assert rows[1][2] == "err, comma"


def test_render_as_csv_preserves_newline_in_message():
    rows = list(
        csv.reader(io.StringIO(render_as_csv([_failure(message="line1\nline2")])))
    )
    assert rows[1][2] == "line1\nline2"


def test_render_as_csv_empty_failures_header_only():
    rows = list(csv.reader(io.StringIO(render_as_csv([]))))
    assert len(rows) == 1


# --- write_report ---


def test_write_report_writes_content(tmp_path):
    path = tmp_path / "report.md"
    write_report("hello", path)
    assert path.read_text(encoding="utf-8") == "hello"


def test_write_report_creates_parent_dirs(tmp_path):
    path = tmp_path / "a" / "b" / "report.md"
    write_report("content", path)
    assert path.exists()


def test_write_report_utf8(tmp_path):
    path = tmp_path / "report.md"
    write_report("héllo wörld", path)
    assert path.read_text(encoding="utf-8") == "héllo wörld"
