from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """An expected API or task-domain error."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class ExternalServiceError(ApiError):
    def __init__(self, service: str, message: str, *, status_code: int = 502) -> None:
        super().__init__(
            "EXTERNAL_SERVICE_ERROR",
            f"{service}：{message}",
            status_code=status_code,
        )


class TaskPaused(Exception):
    """Internal control-flow marker raised at a safe pause point."""

    def __init__(self, reason: str = "user") -> None:
        super().__init__(reason)
        self.reason = reason
