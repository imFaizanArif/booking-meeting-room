"""SSE gateway (ADR 0002). Replays persisted events, then relays pub/sub without gaps."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Header, Query
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from app.api.deps import Auth
from app.core.errors import NotFound, Unauthenticated
from app.core.security import RealtimeClaims, issue_realtime_token, verify_realtime_token
from app.db.session import session_scope
from app.events.bus import get_event_bus
from app.events.schemas import ExecutionEventOut, execution_channel, workspace_channel
from app.models import Execution, ExecutionEvent
from app.schemas.common import Schema

router = APIRouter(prefix="/realtime", tags=["realtime"])
_TOKEN_TTL_S = 120


class RealtimeToken(Schema):
    token: str
    expires_in: int


@router.post("/token", response_model=RealtimeToken)
async def realtime_token(ctx: Auth) -> RealtimeToken:
    return RealtimeToken(token=issue_realtime_token(str(ctx.user_id), str(ctx.workspace_id), _TOKEN_TTL_S),
                         expires_in=_TOKEN_TTL_S)


def _claims(token: str) -> RealtimeClaims:
    claims = verify_realtime_token(token)
    if claims is None:
        raise Unauthenticated("Realtime token is invalid or expired")
    return claims


async def _replay(execution_id: uuid.UUID, after_seq: int) -> list[dict[str, Any]]:
    async with session_scope() as session:
        rows = (await session.scalars(select(ExecutionEvent).where(
            ExecutionEvent.execution_id == execution_id, ExecutionEvent.seq > after_seq)
            .order_by(ExecutionEvent.seq).limit(5000))).all()
        return [ExecutionEventOut.model_validate(r, from_attributes=True).model_dump(mode="json") for r in rows]


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

    async def events() -> AsyncIterator[dict[str, Any]]:
        last = start
        live = get_event_bus().subscribe(execution_channel(execution_id))
        first = asyncio.ensure_future(anext(live))  # subscribe before replaying: no gap
        try:
            for event in await _replay(execution_id, last):
                last = event["seq"]
                yield {"id": str(event["seq"]), "event": event["type"], "data": json.dumps(event)}
            pending = first
            while True:
                message = await pending
                pending = asyncio.ensure_future(anext(live))
                if message.get("type") == "__heartbeat__":
                    yield {"event": "heartbeat", "data": "{}"}
                    continue
                seq = int(message.get("seq", 0))
                if seq <= last:
                    continue
                if seq > last + 1:  # missed something on pub/sub: fill from Postgres
                    for event in await _replay(execution_id, last):
                        last = event["seq"]
                        yield {"id": str(event["seq"]), "event": event["type"], "data": json.dumps(event)}
                    continue
                last = seq
                yield {"id": str(seq), "event": message["type"], "data": json.dumps(message)}
        finally:
            first.cancel()
            await live.aclose()

    return EventSourceResponse(events(), ping=15)


@router.get("/workspace")
async def stream_workspace(token: str = Query(...)) -> EventSourceResponse:
    claims = _claims(token)

    async def events() -> AsyncIterator[dict[str, Any]]:
        live = get_event_bus().subscribe(workspace_channel(claims.workspace_id))
        try:
            async for message in live:
                if message.get("type") == "__heartbeat__":
                    yield {"event": "heartbeat", "data": "{}"}
                    continue
                yield {"event": message.get("type", "message"), "data": json.dumps(message)}
        finally:
            await live.aclose()

    return EventSourceResponse(events(), ping=15)
