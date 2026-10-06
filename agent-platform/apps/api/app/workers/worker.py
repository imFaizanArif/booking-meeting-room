"""arq worker entrypoint: `python -m app.workers.worker` (or `arq app.workers.worker.WorkerSettings`).

One event loop per process; MCP connections are pooled per process and reused across jobs.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from typing import Any

from arq import run_worker

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.redis import get_redis
from app.db.session import dispose_engine, session_scope
from app.llm.base import ProviderConfig
from app.llm.registry import KEYLESS, build_provider
from app.mcp.discovery import upsert_tools
from app.mcp.manager import get_connection_manager
from app.mcp.specs import build_spec, compute_config_hash
from app.models import LLMProvider, MCPServer
from app.notifications.dispatcher import NotificationDispatcher
from app.orchestration.runner import ExecutionRunner, worker_identity
from app.ratelimit.limiter import ConcurrencyLimiter, TokenBucket
from app.secrets.manager import get_secret_manager
from app.workers.checkpointer import open_checkpointer
from app.workers.queue import QUEUE_NAME, ArqQueue, Job, redis_settings

log = get_logger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    stack = contextlib.AsyncExitStack()
    checkpointer = await stack.enter_async_context(open_checkpointer())
    connections = get_connection_manager()
    connections.start_health_checks()
    queue = ArqQueue()
    redis = get_redis()
    ctx.update(
        stack=stack, queue=queue, connections=connections,
        runner=ExecutionRunner(checkpointer=checkpointer, connections=connections, queue=queue,
                               worker_id=worker_identity(), bucket=TokenBucket(redis),
                               concurrency=ConcurrencyLimiter(redis)),
        notifications=NotificationDispatcher(),
    )
    log.info("worker_started", worker=ctx["runner"].worker_id)


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["connections"].shutdown()
    await ctx["queue"].close()
    await ctx["stack"].aclose()
    await dispose_engine()


async def run_execution(ctx: dict[str, Any], execution_id: str) -> str | None:
    status = await ctx["runner"].run(uuid.UUID(execution_id))
    return status.value if status else None


async def resume_execution(ctx: dict[str, Any], execution_id: str, options: dict[str, Any] | None = None) -> str | None:
    status = await ctx["runner"].run(uuid.UUID(execution_id),
                                     operator_resume=bool((options or {}).get("operator_resume")))
    return status.value if status else None


async def discover_server(ctx: dict[str, Any], server_id: str) -> dict[str, Any]:
    connections = ctx["connections"]
    async with session_scope() as session:
        server = await session.get(MCPServer, uuid.UUID(server_id))
        if server is None:
            return {"ok": False, "message": "Server not found"}
        server.config_hash = compute_config_hash(server)
        spec = await build_spec(session, server)
    try:
        conn = await connections.get(spec)
    except Exception as exc:  # noqa: BLE001 - reported to the operator
        return {"ok": False, "message": str(exc)}
    async with session_scope() as session:
        server = await session.get(MCPServer, uuid.UUID(server_id))
        assert server is not None
        report = await upsert_tools(session, server, list(conn.tools.values()))
    return {"ok": True, "message": f"Discovered {len(conn.tools)} tools", "added": report.added,
            "updated": report.updated, "stale": report.stale, "schema_changed": report.schema_changed,
            "server_info": conn.server_info}


async def test_server(ctx: dict[str, Any], server_id: str) -> dict[str, Any]:
    connections = ctx["connections"]
    async with session_scope() as session:
        server = await session.get(MCPServer, uuid.UUID(server_id))
        if server is None:
            return {"ok": False, "message": "Server not found"}
        server.config_hash = compute_config_hash(server)
        spec = await build_spec(session, server)
    try:
        conn = await connections.get(spec)
        await conn.ping()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": f"Connected. {len(conn.tools)} tools available.", "server_info": conn.server_info}


async def test_provider(ctx: dict[str, Any], provider_id: str, model_name: str | None = None) -> dict[str, Any]:
    async with session_scope() as session:
        provider = await session.get(LLMProvider, uuid.UUID(provider_id))
        if provider is None:
            return {"ok": False, "message": "Provider not found"}
        api_key = None
        if provider.api_key_secret_ref and provider.provider_type not in KEYLESS:
            api_key = await get_secret_manager().get(session, provider.workspace_id, provider.api_key_secret_ref)
        config = ProviderConfig(provider_type=provider.provider_type.value, base_url=provider.base_url,
                                api_key=api_key, timeout_s=20.0, metadata=provider.metadata_ or {})
    try:
        message = await asyncio.wait_for(build_provider(config).health(model_name), timeout=25)
        return {"ok": True, "message": message}
    except Exception as exc:  # noqa: BLE001 - shown to the operator, redacted by the API
        return {"ok": False, "message": getattr(exc, "message", None) or f"{type(exc).__name__}: {exc}"}


async def send_notification(ctx: dict[str, Any], approval_id: str) -> dict[str, bool]:
    return await ctx["notifications"].notify_approval(uuid.UUID(approval_id))


class WorkerSettings:
    functions = [run_execution, resume_execution, discover_server, test_server, test_provider, send_notification]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = redis_settings()
    queue_name = QUEUE_NAME
    max_jobs = get_settings().worker_max_jobs
    job_timeout = 60 * 60
    keep_result = 300
    allow_abort_jobs = True


assert {f.__name__ for f in WorkerSettings.functions} == {j.value for j in Job}


def main() -> None:
    run_worker(WorkerSettings)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
