"""Typed application errors and the single error envelope."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.core.enums import ErrorCode

_STATUS: dict[ErrorCode, int] = {
    ErrorCode.validation_error: 422,
    ErrorCode.not_found: 404,
    ErrorCode.conflict: 409,
    ErrorCode.unauthenticated: 401,
    ErrorCode.invalid_credentials: 401,
    ErrorCode.forbidden: 403,
    ErrorCode.csrf_failed: 403,
    ErrorCode.rate_limited: 429,
    ErrorCode.illegal_transition: 409,
    ErrorCode.approval_already_decided: 409,
    ErrorCode.pipeline_invalid: 422,
    ErrorCode.template_error: 422,
    ErrorCode.expression_error: 422,
    ErrorCode.tool_arguments_invalid: 422,
    ErrorCode.ssrf_blocked: 422,
    ErrorCode.secret_not_found: 404,
    ErrorCode.mcp_connection_failed: 502,
    ErrorCode.llm_unavailable: 502,
    ErrorCode.llm_auth_failed: 502,
}


class AppError(Exception):
    """Base class for errors that cross module boundaries.

    `retryable` drives retry logic; it is decided by the error type, never by message text.
    """

    code: ErrorCode = ErrorCode.internal_error
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        details: dict[str, Any] | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable
        self.details = details or {}

    @property
    def http_status(self) -> int:
        return _STATUS.get(self.code, 500 if self.code == ErrorCode.internal_error else 400)

    def to_dict(self) -> dict[str, Any]:
        return {"code": str(self.code), "message": self.message, "details": self.details}


class NotFound(AppError):
    code = ErrorCode.not_found


class Conflict(AppError):
    code = ErrorCode.conflict


class Forbidden(AppError):
    code = ErrorCode.forbidden


class Unauthenticated(AppError):
    code = ErrorCode.unauthenticated


class ValidationFailed(AppError):
    code = ErrorCode.validation_error


class RateLimited(AppError):
    code = ErrorCode.rate_limited
    retryable = True


class IllegalTransition(AppError):
    code = ErrorCode.illegal_transition


class ExecutionCancelled(AppError):
    code = ErrorCode.execution_cancelled


class ErrorBody(BaseModel):
    code: ErrorCode
    message: str
    request_id: str | None = None
    details: dict[str, Any] = {}


class ErrorEnvelope(BaseModel):
    error: ErrorBody
