from __future__ import annotations

from importlib import import_module
from typing import Any


def resolve_attr(
    *,
    name: str,
    module_name: str,
    exports: dict[str, tuple[str, str]],
    extra: str | None = None,
) -> Any:
    target = exports.get(name)
    if target is None:
        raise AttributeError(f"module '{module_name}' has no attribute '{name}'")

    target_module, attr_name = target
    try:
        module = import_module(target_module)
    except ModuleNotFoundError as exc:
        if extra and exc.name and not exc.name.startswith("wordlift_sdk"):
            raise ModuleNotFoundError(
                f"{module_name}.{name} requires optional dependencies from "
                f"'wordlift-sdk[{extra}]'. Install them with "
                f'pip install "wordlift-sdk[{extra}]".'
            ) from exc
        raise

    return getattr(module, attr_name)
