"""FastAPI application: routers, middleware, error envelope, health and metrics."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.routing import APIRoute
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import approvals, auth, executions, hooks, llm, mcp, pipelines, prompts, realtime, schedules
from app.api.v1 import settings as settings_routes
from app.core.config import get_settings
from app.core.enums import ErrorCode
from app.core.errors import AppError, ErrorEnvelope
from app.core.logging import bind_context, clear_context, configure_logging, get_logger
from app.core.redis import close_redis, get_redis
from app.db.session import dispose_engine, session_scope
from app.workers.queue import get_queue

log = get_logger(__name__)
REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency", ["method", "route"])
_HTTP_CODES = {400: ErrorCode.validation_error, 401: ErrorCode.unauthenticated, 403: ErrorCode.forbidden,
               404: ErrorCode.not_found, 405: ErrorCode.validation_error, 409: ErrorCode.conflict,
               429: ErrorCode.rate_limited}


def _envelope(status: int, code: ErrorCode, message: str, request: Request, details: dict | None = None) -> JSONResponse:
    body = {"error": {"code": code.value, "message": message,
                      "request_id": getattr(request.state, "request_id", None), "details": details or {}}}
    return JSONResponse(status_code=status, content=body)


def _operation_id(route: APIRoute) -> str:
    return route.name


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    yield
    queue = get_queue()
    close = getattr(queue, "close", None)
    if close is not None:
        await close()
    await close_redis()
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Agent Platform API",
        version="0.1.0",
        description="Control plane for autonomous agent pipelines. All errors use the ErrorEnvelope schema.",
        lifespan=lifespan,
        generate_unique_id_function=_operation_id,
        responses={422: {"model": ErrorEnvelope}, 401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope},
                   404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}},
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id[:64]
        clear_context()
        bind_context(request_id=request.state.request_id)
        started = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")
        REQUESTS.labels(request.method, path, response.status_code).inc()
        LATENCY.labels(request.method, path).observe(time.perf_counter() - started)
        response.headers["x-request-id"] = request.state.request_id
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["x-frame-options"] = "DENY"
        response.headers["referrer-policy"] = "strict-origin-when-cross-origin"
        response.headers["cache-control"] = response.headers.get("cache-control", "no-store")
        return response

    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["content-type", "x-csrf-token", "x-request-id"],
    )

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        if exc.http_status >= 500:
            log.error("app_error", code=exc.code.value, message=exc.message)
        return _envelope(exc.http_status, exc.code, exc.message, request, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [{"field": ".".join(str(p) for p in err["loc"] if p not in ("body", "query", "path")),
                   "message": err["msg"]} for err in exc.errors()[:50]]
        return _envelope(422, ErrorCode.validation_error, "Some fields are invalid", request, {"fields": fields})

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, ErrorCode.internal_error)
        return _envelope(exc.status_code, code, str(exc.detail), request)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", error=type(exc).__name__)
        return _envelope(500, ErrorCode.internal_error, "Something went wrong. Quote the request id when reporting it.",
                         request)

    for module in (auth, llm, mcp, prompts, pipelines, executions, approvals, schedules, settings_routes, realtime,
                   hooks):
        app.include_router(module.router, prefix="/api/v1")

    @app.get("/healthz", tags=["ops"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["ops"])
    async def readyz() -> JSONResponse:
        checks: dict[str, str] = {}
        try:
            async with session_scope() as session:
                await session.execute(text("select 1"))
            checks["postgres"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["postgres"] = f"error: {type(exc).__name__}"
        try:
            await get_redis().ping()
            checks["redis"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["redis"] = f"error: {type(exc).__name__}"
        ok = all(v == "ok" for v in checks.values())
        return JSONResponse(status_code=200 if ok else 503, content={"status": "ok" if ok else "degraded", **checks})

    @app.get("/metrics", tags=["ops"], include_in_schema=False)
    async def metrics() -> PlainTextResponse:
        return PlainTextResponse(generate_latest().decode(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
