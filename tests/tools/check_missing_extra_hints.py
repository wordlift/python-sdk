from __future__ import annotations

import importlib


CHECKS: list[tuple[str, str, str]] = [
    ("wordlift_sdk.validation", "validate_file", "validation"),
    ("wordlift_sdk.ingestion", "run_ingestion", "ingestion"),
    ("wordlift_sdk.structured_data", "CreateRequest", "structured-data"),
    ("wordlift_sdk", "run_kg_import_workflow", "workflow"),
    ("wordlift_sdk.kg_build", "run_cloud_workflow", "kg-build"),
]


def main() -> int:
    for module_name, attr_name, extra_name in CHECKS:
        module = importlib.import_module(module_name)
        try:
            getattr(module, attr_name)
        except ModuleNotFoundError as exc:
            message = str(exc)
            expected = f"wordlift-sdk[{extra_name}]"
            if expected not in message:
                raise AssertionError(
                    f"{module_name}.{attr_name} failed without expected hint "
                    f"'{expected}': {message}"
                ) from exc
            print(f"hint ok: {module_name}.{attr_name} -> {expected}")
            continue

        raise AssertionError(
            f"{module_name}.{attr_name} unexpectedly resolved without requiring "
            f"extra '{extra_name}'."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
