"""SSE gateway (ADR 0002). Replays persisted events, then relays pub/sub without gaps."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

from fastapi import APIRouter, Header, Query
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from app.api.deps import Auth
from app.core.errors import NotFound, Unauthenticated
from app.core.security import RealtimeClaims, issue_realtime_token, verify_realtime_token
from app.db.session import session_scope
from app.events.bus import HEARTBEAT, SUBSCRIBED, get_event_bus
from app.events.schemas import ExecutionEventOut, execution_channel, workspace_channel
from app.models import Execution, ExecutionEvent
from app.schemas.common import Schema

router = APIRouter(prefix="/realtime", tags=["realtime"])
_TOKEN_TTL_S = 120


class RealtimeToken(Schema):
    token: str
    expires_in: int


# `no-transform` stops proxies that compress (the Next.js rewrite proxy, CDNs) from buffering the
# stream until it ends.
SSE_HEADERS = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}


@router.post("/token", response_model=RealtimeToken)
async def realtime_token(ctx: Auth) -> RealtimeToken:
    return RealtimeToken(
        token=issue_realtime_token(str(ctx.user_id), str(ctx.workspace_id), _TOKEN_TTL_S), expires_in=_TOKEN_TTL_S
    )


def _claims(token: str) -> RealtimeClaims:
    claims = verify_realtime_token(token)
    if claims is None:
        raise Unauthenticated("Realtime token is invalid or expired")
    return claims


_REPLAY_BATCH = 5000


async def _replay(execution_id: uuid.UUID, after_seq: int) -> AsyncIterator[dict[str, Any]]:
    """Every persisted event with `seq > after_seq`, in order, in batches."""
    while True:
        async with session_scope() as session:
            rows = (
                await session.scalars(
                    select(ExecutionEvent)
                    .where(ExecutionEvent.execution_id == execution_id, ExecutionEvent.seq > after_seq)
                    .order_by(ExecutionEvent.seq)
                    .limit(_REPLAY_BATCH)
                )
            ).all()
            batch = [ExecutionEventOut.model_validate(r, from_attributes=True).model_dump(mode="json") for r in rows]
        for event in batch:
            yield event
        if len(batch) < _REPLAY_BATCH:
            return
        after_seq = batch[-1]["seq"]


def _sse(event: dict[str, Any]) -> dict[str, str]:
    return {"id": str(event["seq"]), "event": event["type"], "data": json.dumps(event)}


async def execution_events(execution_id: uuid.UUID, after_seq: int) -> AsyncGenerator[dict[str, str]]:
    """SSE messages for one execution: persisted history after `after_seq`, then live, gap-free.

    Events are committed before they are published, so subscribing *before* reading history
    means any event is either in the replay or arrives live; duplicates are dropped by `seq`, and
    a jump in `seq` (a lost pub/sub message) is filled from Postgres.
    """
    last = after_seq
    live = get_event_bus().subscribe(execution_channel(execution_id))
    try:
        ready = await anext(live)
        if ready.get("type") != SUBSCRIBED:
            raise RuntimeError(f"event bus yielded {ready!r} before confirming the subscription")
        async for event in _replay(execution_id, last):
            last = event["seq"]
            yield _sse(event)
        async for message in live:
            if message.get("type") == HEARTBEAT:
                yield {"event": "heartbeat", "data": "{}"}
                continue
            seq = int(message.get("seq", 0))
            if seq <= last:
                continue
            if seq > last + 1:  # missed something on pub/sub: fill from Postgres
                async for event in _replay(execution_id, last):
                    last = event["seq"]
                    yield _sse(event)
                continue
            last = seq
            yield _sse(message)
    finally:
        await live.aclose()


@router.get("/executions/{execution_id}")
async def stream_execution(
    execution_id: uuid.UUID,
    token: str = Query(...),
    after_seq: int = Query(0, ge=0),
    last_event_id: str | None = Header(default=None),
) -> EventSourceResponse:
    claims = _claims(token)
    async with session_scope() as session:
        owner = await session.scalar(select(Execution.workspace_id).where(Execution.id == execution_id))
    if owner is None or str(owner) != claims.workspace_id:
        raise NotFound("Execution not found")
    start = int(last_event_id) if last_event_id and last_event_id.isdigit() else after_seq
    return EventSourceResponse(execution_events(execution_id, start), ping=15, headers=SSE_HEADERS)


@router.get("/workspace")
async def stream_workspace(token: str = Query(...)) -> EventSourceResponse:
    claims = _claims(token)

    async def events() -> AsyncIterator[dict[str, Any]]:
        live = get_event_bus().subscribe(workspace_channel(claims.workspace_id))
        try:
            async for message in live:
                if message.get("type") == SUBSCRIBED:
                    continue
                if message.get("type") == HEARTBEAT:
                    yield {"event": "heartbeat", "data": "{}"}
                    continue
                yield {"event": message.get("type", "message"), "data": json.dumps(message)}
        finally:
            await live.aclose()

    return EventSourceResponse(events(), ping=15, headers=SSE_HEADERS)
