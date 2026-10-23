from pathlib import Path


def test_retry_handlers_use_public_pydantic_core_validation_error() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    targets = [
        "wordlift_sdk/workflow/url_handler/search_console_url_handler.py",
    ]

    for target in targets:
        content = (repo_root / target).read_text()
        assert "pydantic_core.ValidationError" in content
        assert "pydantic_core._pydantic_core.ValidationError" not in content
