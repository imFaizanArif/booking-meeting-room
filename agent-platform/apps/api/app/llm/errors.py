"""Typed LLM error taxonomy. Retry decisions use the type, never message text."""

from __future__ import annotations

from app.core.enums import ErrorCode
from app.core.errors import AppError


class LLMError(AppError):
    code = ErrorCode.llm_invalid_request


class RateLimitedError(LLMError):
    code = ErrorCode.llm_rate_limited
    retryable = True


class TimeoutError_(LLMError):  # noqa: N801  (avoid shadowing the builtin)
    code = ErrorCode.llm_timeout
    retryable = True


class ProviderUnavailable(LLMError):
    code = ErrorCode.llm_unavailable
    retryable = True


class AuthFailed(LLMError):
    code = ErrorCode.llm_auth_failed


class InvalidRequest(LLMError):
    code = ErrorCode.llm_invalid_request


class ContextTooLong(LLMError):
    code = ErrorCode.llm_context_too_long


class ContentFiltered(LLMError):
    code = ErrorCode.llm_content_filtered


def from_http_status(status: int, message: str, *, provider: str) -> LLMError:
    details = {"provider": provider, "status": status}
    if status == 429:
        return RateLimitedError(message, details=details)
    if status in (401, 403):
        return AuthFailed(message, details=details)
    if status in (408, 504):
        return TimeoutError_(message, details=details)
    if status == 413:
        return ContextTooLong(message, details=details)
    if status >= 500:
        return ProviderUnavailable(message, details=details)
    return InvalidRequest(message, details=details)
