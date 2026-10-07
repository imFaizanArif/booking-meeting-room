"""execution_events carry a gap-free sequence per execution, and the SSE stream delivers it without gaps."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

import pytest
from sqlalchemy import select

from app.api.v1 import realtime
from app.core.enums import DecisionAction, EventType, ExecutionStatus
from app.db.session import session_scope
from app.events import bus as event_bus
from app.events.bus import SUBSCRIBED
from app.events.publisher import publish_execution_event
from app.events.schemas import execution_channel
from app.models import ExecutionEvent
from app.services.context import AuthContext
from tests.conftest import RunnerFactory
from tests.helpers import db_execution, decide_as, event_seqs, pending_approval, start_demo


async def test_sequence_is_gap_free_across_pause_and_resume(
    operator_ctx: AuthContext,
    runners: RunnerFactory,
) -> None:
    execution_id = await start_demo(operator_ctx)
    await runners.new().run(execution_id)
    paused_seqs = await event_seqs(execution_id)
    assert paused_seqs == list(range(1, len(paused_seqs) + 1))

    await decide_as(operator_ctx, (await pending_approval(execution_id)).id, DecisionAction.approve)
    assert await runners.new().run(execution_id) == ExecutionStatus.completed
    seqs = await event_seqs(execution_id)
    assert seqs == list(range(1, len(seqs) + 1))
    assert len(seqs) > len(paused_seqs)
    assert (await db_execution(execution_id)).last_event_seq == len(seqs)

    async with session_scope() as session:
        types = list(
            (
                await session.scalars(
                    select(ExecutionEvent.type)
                    .where(ExecutionEvent.execution_id == execution_id)
                    .order_by(ExecutionEvent.seq)
                )
            ).all()
        )
    assert types[0] == EventType.execution_created
    assert types[-1] == EventType.execution_completed
    for expected in (
        EventType.approval_created,
        EventType.approval_decided,
        EventType.tool_awaiting_approval,
        EventType.tool_approved,
        EventType.execution_paused,
    ):
        assert expected in types


# ---- SSE gateway: replay then live, without gaps or duplicates -----------------------------------


class ScriptedBus:
    """In-memory EventBus whose delivery the test controls: drop, duplicate or reorder by seq."""

    def __init__(self, log: list[str]) -> None:
        self.log = log
        self.queues: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}
        self.drop: set[int] = set()
        self.held: list[dict[str, Any]] = []
        self.hold: set[int] = set()

    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        seq = message.get("seq")
        if seq in self.drop:
            return
        if seq in self.hold:
            self.held.append(message)
            return
        self.deliver(channel, message)

    def deliver(self, channel: str, message: dict[str, Any]) -> None:
        for queue in self.queues.get(channel, []):
            queue.put_nowait(message)

    async def subscribe(self, *channels: str) -> AsyncGenerator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        for channel in channels:
            self.queues.setdefault(channel, []).append(queue)
        self.log.append("subscribed")
        try:
            yield {"type": SUBSCRIBED}
            while True:
                yield await queue.get()
        finally:
            for channel in channels:
                self.queues[channel].remove(queue)


async def _take_until(stream: AsyncGenerator[dict[str, str]], last_seq: int) -> list[int]:
    seqs: list[int] = []
    while not seqs or seqs[-1] < last_seq:
        message = await asyncio.wait_for(anext(stream), timeout=5)
        if "id" in message:
            seqs.append(int(message["id"]))
            assert json.loads(message["data"])["seq"] == seqs[-1]
    return seqs


async def test_sse_stream_is_gap_free_across_replay_and_live(
    operator_ctx: AuthContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_id = await start_demo(operator_ctx)
    row = await db_execution(execution_id)
    history = len(await event_seqs(execution_id))
    assert history >= 1

    log: list[str] = []
    bus = ScriptedBus(log)
    monkeypatch.setattr(event_bus, "_bus", bus)
    channel = execution_channel(execution_id)

    async def publish(node: str) -> int:
        out = await publish_execution_event(
            workspace_id=row.workspace_id, execution_id=execution_id, type=EventType.node_started, node_id=node
        )
        return out.seq

    original_replay = realtime._replay
    replays = 0

    async def replay_then_publish(execution: uuid.UUID, after_seq: int) -> AsyncIterator[dict[str, Any]]:
        # An event committed right after the history query ran: it must still arrive (live).
        nonlocal replays
        replays += 1
        log.append("replay")
        async for event in original_replay(execution, after_seq):
            yield event
        if replays == 1:
            await publish("committed-after-replay")

    monkeypatch.setattr(realtime, "_replay", replay_then_publish)
    stream = realtime.execution_events(execution_id, 0)
    try:
        assert await _take_until(stream, history + 1) == list(range(1, history + 2))
        assert log[:2] == ["subscribed", "replay"], "must subscribe before reading history"

        # Live: one message lost, one late and one duplicated on pub/sub.
        a = history + 2
        bus.drop.add(a + 1)
        bus.hold.add(a + 2)
        for node in ("a", "b", "c", "d"):
            await publish(node)
        for late in bus.held:
            bus.deliver(channel, late)  # out of order: arrives after a+3
        assert await _take_until(stream, a + 3) == list(range(history + 2, a + 4))
        bus.deliver(channel, {"seq": a, "type": "node.started"})  # duplicate of an old one
        last = await publish("e")
        assert await _take_until(stream, last) == [last]
    finally:
        await stream.aclose()
    assert bus.queues[channel] == []

    # Reconnect with Last-Event-ID: exactly the tail, from Postgres.
    resumed = realtime.execution_events(execution_id, last - 3)
    try:
        assert await _take_until(resumed, last) == [last - 2, last - 1, last]
    finally:
        await resumed.aclose()
    assert await event_seqs(execution_id) == list(range(1, last + 1))


async def test_redis_bus_subscription_is_live_once_confirmed() -> None:
    bus = event_bus.RedisEventBus()
    channel = f"test:{uuid.uuid4().hex}"
    stream = bus.subscribe(channel)
    try:
        assert await anext(stream) == {"type": SUBSCRIBED}
        await bus.publish(channel, {"seq": 1})  # published immediately after: never lost
        assert await asyncio.wait_for(anext(stream), timeout=5) == {"seq": 1}
    finally:
        await stream.aclose()


async def test_sse_responses_are_not_buffered_by_proxies(operator_ctx: AuthContext) -> None:
    from app.core.security import issue_realtime_token

    execution_id = await start_demo(operator_ctx)
    token = issue_realtime_token(str(operator_ctx.user_id), str(operator_ctx.workspace_id))
    for response in (
        await realtime.stream_execution(execution_id, token=token, after_seq=0, last_event_id=None),
        await realtime.stream_workspace(token=token),
    ):
        try:
            assert "no-transform" in response.headers["cache-control"]
            assert response.headers["x-accel-buffering"] == "no"
        finally:
            await response.body_iterator.aclose()  # never iterated: just release the subscription
