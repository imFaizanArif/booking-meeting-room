"""No API path executes an approval-gated tool without a human decision."""

from __future__ import annotations

import re
import uuid
from typing import Any

from fastapi.routing import APIRoute
from mock_mcp.common import effects

from app.core.enums import ExecutionStatus
from app.main import app
from app.schemas.config import MCPToolBulk, MCPToolPatch
from app.services.context import AuthContext
from app.workers.queue import Job
from tests.api.conftest import Login, assert_envelope
from tests.conftest import FakeQueue, RunnerFactory
from tests.helpers import SUBMIT, pending_approval, submit_calls

V1 = "/api/v1"


def _graph() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "trigger", "type": "trigger", "name": "Start", "config": {}},
            {"id": "submit", "type": "mcp_tool", "name": "Submit directly", "error_policy": {"mode": "fail"},
             "config": {"tool": SUBMIT, "arguments": {
                 "job_id": "job-103", "hourly_rate": 110,
                 "cover_letter": "Submitted straight from a pipeline step, no agent involved."}}},
            {"id": "end", "type": "end", "name": "End", "config": {"output": "=nodes.submit.output"}},
        ],
        "edges": [{"id": "e1", "source": "trigger", "target": "submit"},
                  {"id": "e2", "source": "submit", "target": "end"}],
    }


async def _submit_tool_id(client: Any) -> str:
    tools = (await client.get(f"{V1}/mcp/tools")).json()
    return next(t["id"] for t in tools if t["namespaced_name"] == SUBMIT)


async def test_mcp_tool_node_waits_for_approval(
    login: Login, operator_ctx: AuthContext, runners: RunnerFactory, fake_queue: FakeQueue,
) -> None:
    operator = await login("operator@example.com")
    viewer = await login("viewer@example.com")
    created = await operator.post(f"{V1}/pipelines", json={"name": f"Direct submit {uuid.uuid4().hex[:6]}",
                                                           "graph": _graph()})
    assert created.status_code == 201, created.text
    pipeline_id = created.json()["id"]

    started = await operator.post(f"{V1}/pipelines/{pipeline_id}/run", json={"input": {}})
    assert started.status_code == 202 and started.json()["status"] == "queued"
    execution_id = uuid.UUID(started.json()["id"])
    assert fake_queue.of(Job.run_execution) == [(str(execution_id),)]  # the API only enqueues
    assert effects("jobs") == []

    assert await runners.new().run(execution_id) == ExecutionStatus.paused_for_review
    assert effects("jobs") == []
    approval = await pending_approval(execution_id)
    [call] = await submit_calls(execution_id)
    assert call.status == "awaiting_approval"

    # Every other lever is refused while the approval is pending.
    for action in ("resume", "retry"):
        assert_envelope(await operator.post(f"{V1}/executions/{execution_id}/control", json={"action": action}),
                        409, "ILLEGAL_TRANSITION")
    assert_envelope(await viewer.post(f"{V1}/approvals/{approval.id}/decision", json={"action": "approve"}),
                    403, "FORBIDDEN")
    tool_id = await _submit_tool_id(operator)
    assert_envelope(await viewer.patch(f"{V1}/mcp/tools/{tool_id}", json={"requires_approval": False}),
                    403, "FORBIDDEN")
    # Re-running the worker without a decision does not execute anything.
    assert await runners.new().run(execution_id) is None  # not in a runnable state
    assert effects("jobs") == []

    # A restart is a new execution that pauses again.
    restarted = await operator.post(f"{V1}/executions/{execution_id}/restart")
    assert restarted.status_code == 202
    restart_id = uuid.UUID(restarted.json()["id"])
    assert await runners.new().run(restart_id) == ExecutionStatus.paused_for_review
    assert effects("jobs") == []

    decided = await operator.post(f"{V1}/approvals/{approval.id}/decision", json={"action": "approve"})
    assert decided.status_code == 200 and decided.json()["status"] == "approved"
    assert await runners.new().run(execution_id) == ExecutionStatus.completed
    [effect] = effects("jobs")
    assert effect["result"]["job_id"] == "job-103"
    detail = (await operator.get(f"{V1}/executions/{execution_id}")).json()
    assert detail["execution"]["output"]["status"] == "submitted"


async def test_destructive_tool_stays_gated_when_requires_approval_is_cleared(
    login: Login, operator_ctx: AuthContext, runners: RunnerFactory,
) -> None:
    operator = await login("operator@example.com")
    tool_id = await _submit_tool_id(operator)
    relaxed = await operator.patch(f"{V1}/mcp/tools/{tool_id}", json={"requires_approval": False})
    assert relaxed.status_code == 200 and relaxed.json()["is_destructive"] is True
    try:
        created = await operator.post(f"{V1}/pipelines", json={"name": f"Relaxed {uuid.uuid4().hex[:6]}",
                                                               "graph": _graph()})
        started = await operator.post(f"{V1}/pipelines/{created.json()['id']}/run", json={"input": {}})
        execution_id = uuid.UUID(started.json()["id"])
        assert await runners.new().run(execution_id) == ExecutionStatus.paused_for_review
        approval = await pending_approval(execution_id)
        assert approval.reasons == ["Tool is marked destructive"]
        assert effects("jobs") == []
    finally:
        await operator.patch(f"{V1}/mcp/tools/{tool_id}", json={"requires_approval": True})


def _routes() -> list[tuple[str, str]]:
    """(METHOD, path) for every API operation, from the OpenAPI contract the web app is generated from."""
    out = []
    for path, operations in app.openapi()["paths"].items():
        out.extend((method.upper(), path) for method in operations)
    return sorted(out)


def _hidden_routes() -> list[str]:
    """Routes left out of the OpenAPI schema would escape the check above; there must be none."""
    hidden = []
    stack: list[Any] = list(app.routes)
    while stack:
        route = stack.pop()
        if hasattr(route, "original_router"):
            stack.extend(route.original_router.routes)
        elif isinstance(route, APIRoute) and not route.include_in_schema:
            hidden.append(route.path)
    return hidden


def test_no_endpoint_executes_tools_directly() -> None:
    routes = _routes()
    assert len(routes) > 50
    assert _hidden_routes() == ["/metrics"]  # GET-only Prometheus scrape
    verbs = re.compile(r"/(call|calls|invoke|execute|exec|run[-_]tool|tools/[^/]+/(run|call))(/|$)")
    assert [p for _, p in routes if verbs.search(p)] == []
    mutating_tool_routes = [(m, p) for m, p in routes if "/mcp/tools" in p and m != "GET"]
    assert mutating_tool_routes == [("PATCH", f"{V1}/mcp/tools/{{tool_id}}"), ("POST", f"{V1}/mcp/tools/bulk")]
    # Those two only change flags; neither accepts arguments to run.
    assert set(MCPToolPatch.model_fields) == {"is_enabled", "requires_approval", "is_destructive", "risk_level"}
    assert set(MCPToolBulk.model_fields) == {"tool_ids", "patch"}
    # The only ways to start work are runs of saved pipelines (and restarts of executions).
    starts = sorted(p for m, p in routes if m == "POST" and p.endswith(("/run", "/restart")))
    assert starts == [f"{V1}/executions/{{execution_id}}/restart", f"{V1}/pipelines/{{pipeline_id}}/run"]
