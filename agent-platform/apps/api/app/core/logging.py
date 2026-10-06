"""structlog configuration with contextvar propagation and redaction."""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog

from app.core.redaction import redactor

LOG_CONTEXT_KEYS = (
    "request_id",
    "workspace_id",
    "user_id",
    "execution_id",
    "pipeline_version_id",
    "node_id",
    "tool_call_id",
)
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def bind_context(**values: Any) -> None:
    structlog.contextvars.bind_contextvars(
        **{k: str(v) for k, v in values.items() if v is not None and k in LOG_CONTEXT_KEYS}
    )


def clear_context() -> None:
    structlog.contextvars.clear_contextvars()


def current_context() -> dict[str, str]:
    ctx = structlog.contextvars.get_contextvars()
    return {k: v for k, v in ctx.items() if k in LOG_CONTEXT_KEYS}


def _redact_processor(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    return redactor.redact(event_dict)  # type: ignore[no-any-return]


def configure_logging(level: str = "INFO", json: bool = True) -> None:
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _redact_processor,
    ]
    renderer: Any = (
        structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(level=level.upper(), stream=sys.stdout, format="%(message)s")
    for noisy in ("httpx", "httpcore", "httpx2", "mcp"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
