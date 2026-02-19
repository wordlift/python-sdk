from __future__ import annotations

from typing import Any


class IngestionError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.details = details or {}


class IngestionConfigError(IngestionError):
    pass


class SourceConfigError(IngestionConfigError):
    pass


class SourceRuntimeError(IngestionError):
    pass


class LoaderConfigError(IngestionConfigError):
    pass


class LoaderRuntimeError(IngestionError):
    pass
