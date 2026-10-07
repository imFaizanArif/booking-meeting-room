"""Approval decisions over HTTP: concurrency, and event replay by sequence."""

from __future__ import annotations

import asyncio

from mock_mcp.common import effects
from sqlalchemy import func, select

from app.core.enums import AuditEventType, EventType, ExecutionStatus
from app.db.session import session_scope
from app.models import AuditEvent, ExecutionEvent
from app.services.context import AuthContext
from app.workers.queue import Job
from tests.api.conftest import Login, assert_envelope
from tests.conftest import FakeQueue, RunnerFactory
from tests.helpers import event_seqs, pending_approval, start_demo, submit_calls

V1 = "/api/v1"


async def test_double_approval_race_has_one_winner(
    login: Login,
    operator_ctx: AuthContext,
    runners: RunnerFactory,
    fake_queue: FakeQueue,
) -> None:
    execution_id = await start_demo(operator_ctx)
    await runners.new().run(execution_id)
    approval = await pending_approval(execution_id)
    alice = await login("operator@example.com")
    bob = await login("admin@example.com")
    fake_queue.clear()

    responses = await asyncio.gather(
        alice.post(f"{V1}/approvals/{approval.id}/decision", json={"action": "approve"}),
        bob.post(f"{V1}/approvals/{approval.id}/decision", json={"action": "reject", "reason": "Not this one"}),
    )
    codes = sorted(r.status_code for r in responses)
    assert codes == [200, 409], [r.text for r in responses]
    winner = next(r for r in responses if r.status_code == 200).json()
    loser = next(r for r in responses if r.status_code == 409)
    error = assert_envelope(loser, 409, "APPROVAL_ALREADY_DECIDED")
    assert error["details"]["status"] == winner["status"]
    # Only the winner's side effects happened: one decided event, one audit row, one resume.
    assert fake_queue.of(Job.resume_execution) == [(str(execution_id),)]
    async with session_scope() as session:
        decided_events = await session.scalar(
            select(func.count())
            .select_from(ExecutionEvent)
            .where(ExecutionEvent.execution_id == execution_id, ExecutionEvent.type == EventType.approval_decided)
        )
        decided_audits = await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.entity_id == str(approval.id), AuditEvent.event_type == AuditEventType.approval_decided)
        )
    assert (decided_events, decided_audits) == (1, 1)

    # Once decided, any further decision is refused too.
    assert_envelope(
        await alice.post(f"{V1}/approvals/{approval.id}/decision", json={"action": "approve"}),
        409,
        "APPROVAL_ALREADY_DECIDED",
    )
    final = await runners.new().run(execution_id)
    assert final == ExecutionStatus.completed
    assert len(effects("jobs")) == (1 if winner["status"] == "approved" else 0)


async def test_decision_validation_errors(login: Login, operator_ctx: AuthContext, runners: RunnerFactory) -> None:
    execution_id = await start_demo(operator_ctx)
    await runners.new().run(execution_id)
    approval = await pending_approval(execution_id)
    client = await login("operator@example.com")
    url = f"{V1}/approvals/{approval.id}/decision"
    assert_envelope(await client.post(url, json={"action": "reject"}), 422, "VALIDATION_ERROR")
    assert_envelope(await client.post(url, json={"action": "mark_succeeded"}), 422, "VALIDATION_ERROR")
    assert_envelope(await client.post(url, json={"action": "launch"}), 422, "VALIDATION_ERROR")
    edit = await client.post(url, json={"action": "edit", "edited_arguments": {"job_id": 7}})
    fields = {f["field"] for f in assert_envelope(edit, 422, "VALIDATION_ERROR")["details"]["fields"]}
    assert {"job_id", "cover_letter", "hourly_rate"} <= fields
    [call] = await submit_calls(execution_id)
    detail = (await client.get(f"{V1}/approvals/{approval.id}")).json()
    assert detail["status"] == "pending" and detail["tool_call"]["id"] == str(call.id)
    assert detail["input_schema"]["required"] == ["job_id", "cover_letter", "hourly_rate"]


async def test_events_after_seq_returns_exact_tail(
    login: Login,
    operator_ctx: AuthContext,
    runners: RunnerFactory,
) -> None:
    execution_id = await start_demo(operator_ctx)
    await runners.new().run(execution_id)
    seqs = await event_seqs(execution_id)
    total = len(seqs)
    assert seqs == list(range(1, total + 1))
    client = await login("viewer@example.com")

    everything = (await client.get(f"{V1}/executions/{execution_id}/events")).json()
    assert [e["seq"] for e in everything] == seqs
    for k in (0, 1, total // 2, total - 1, total):
        tail = (await client.get(f"{V1}/executions/{execution_id}/events", params={"after_seq": k})).json()
        assert [e["seq"] for e in tail] == list(range(k + 1, total + 1))
        assert [e["id"] for e in tail] == [e["id"] for e in everything[k:]]
    limited = (await client.get(f"{V1}/executions/{execution_id}/events", params={"after_seq": 2, "limit": 3})).json()
    assert [e["seq"] for e in limited] == [3, 4, 5]
