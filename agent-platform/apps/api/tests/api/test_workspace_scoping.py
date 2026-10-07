"""Data from another workspace is invisible (404), never forbidden-but-revealed."""

from __future__ import annotations

import uuid

from app.core.enums import Role
from app.core.security import hash_password
from app.db.session import session_scope
from app.models import User, Workspace, WorkspaceMember
from app.services.context import AuthContext
from tests.api.conftest import Login, assert_envelope, login_client
from tests.conftest import RunnerFactory
from tests.helpers import demo_pipeline_id, pending_approval, start_demo

V1 = "/api/v1"


async def _outsider() -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:8]
    email, password = f"outsider-{suffix}@example.com", "outsider-password"
    async with session_scope() as session:
        ws = Workspace(name=f"Other {suffix}", slug=f"other_{suffix}", settings={})
        user = User(email=email, display_name="Outsider", password_hash=hash_password(password))
        session.add_all([ws, user])
        await session.flush()
        session.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=Role.owner))
    return email, password


async def test_other_workspace_sees_404(login: Login, operator_ctx: AuthContext, runners: RunnerFactory) -> None:
    execution_id = await start_demo(operator_ctx)
    await runners.new().run(execution_id)
    approval = await pending_approval(execution_id)
    pipeline_id = await demo_pipeline_id()

    email, password = await _outsider()
    outsider = await login_client(email, password)
    try:
        for path in (f"/pipelines/{pipeline_id}", f"/executions/{execution_id}",
                     f"/executions/{execution_id}/events", f"/approvals/{approval.id}"):
            assert_envelope(await outsider.get(f"{V1}{path}"), 404, "NOT_FOUND")
        assert_envelope(await outsider.post(f"{V1}/approvals/{approval.id}/decision", json={"action": "approve"}),
                        404, "NOT_FOUND")
        assert_envelope(await outsider.post(f"{V1}/pipelines/{pipeline_id}/run", json={"input": {}}),
                        404, "NOT_FOUND")
        assert_envelope(await outsider.post(f"{V1}/executions/{execution_id}/control", json={"action": "cancel"}),
                        404, "NOT_FOUND")
        assert (await outsider.get(f"{V1}/pipelines")).json() == []
        assert (await outsider.get(f"{V1}/approvals")).json()["total"] == 0
        assert (await outsider.get(f"{V1}/executions")).json()["total"] == 0
        assert (await outsider.get(f"{V1}/mcp/tools")).json() == []
    finally:
        await outsider.aclose()

    # The owner's view is unaffected.
    insider = await login("operator@example.com")
    assert (await insider.get(f"{V1}/approvals/{approval.id}")).json()["status"] == "pending"
