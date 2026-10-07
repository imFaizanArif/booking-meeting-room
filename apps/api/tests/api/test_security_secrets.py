"""Secret values never leave the secret store: not in responses, audit, events, snapshots or logs."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
import sqlalchemy as sa

from app.core.enums import ExecutionStatus, ProviderType
from app.core.logging import get_logger
from app.db.session import session_scope
from app.llm import registry
from app.llm.adapters.fake import FakeLLMProvider
from app.services.context import AuthContext
from tests.api.conftest import Login
from tests.conftest import LOG_SINK, RunnerFactory

V1 = "/api/v1"
API_KEY = "sk-test-SECRET-VALUE-123456"
HEADER_SECRET = "hdr-SECRET-VALUE-654321"
SECRETS = (API_KEY, HEADER_SECRET)


class Recorder:
    """Wraps a client and keeps every response body for the final scan."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self.bodies: list[str] = []

    async def __call__(self, method: str, path: str, expect: int = 200, **kwargs: Any) -> Any:
        response = await self.client.request(method, f"{V1}{path}", **kwargs)
        self.bodies.append(response.text)
        assert response.status_code == expect, response.text
        return response.json()


def _graph(model_id: str) -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "trigger", "type": "trigger", "name": "Start", "config": {}},
            {
                "id": "ask",
                "type": "llm",
                "name": "Ask",
                "config": {
                    "model_id": model_id,
                    "user_prompt": "Say hello to {{ my_name }}",
                    "provider_extras": {"fake": {"script": ['{"content": "Hello!"}']}},
                },
            },
            {"id": "end", "type": "end", "name": "End", "config": {"output": "=nodes.ask.output"}},
        ],
        "edges": [{"id": "e1", "source": "trigger", "target": "ask"}, {"id": "e2", "source": "ask", "target": "end"}],
    }


async def _scan_db() -> dict[str, int]:
    queries = {
        "audit_events.payload": "SELECT payload::text FROM audit_events",
        "execution_events.payload": "SELECT payload::text FROM execution_events",
        "executions.config_snapshot": "SELECT config_snapshot::text FROM executions",
        "executions.output_error": "SELECT coalesce(output::text, '') || coalesce(error::text, '') FROM executions",
        "approvals": "SELECT coalesce(payload::text, '') || coalesce(original_arguments::text, '') FROM approvals",
        "mcp_servers": "SELECT coalesce(env_refs::text, '') || coalesce(header_refs::text, '') FROM mcp_servers",
        "llm_providers": "SELECT coalesce(api_key_secret_ref, '') || metadata::text FROM llm_providers",
        "llm_usage.summary": "SELECT coalesce(summary, '') FROM llm_usage",
        "secrets.hint": "SELECT hint FROM secrets",
    }
    found: dict[str, int] = {}
    async with session_scope() as session:
        for name, query in queries.items():
            texts = (await session.scalars(sa.text(query))).all()
            found[name] = sum(1 for t in texts for s in SECRETS if s in (t or ""))
    return found


async def _scan_every_table(needles: tuple[str, ...] = SECRETS) -> dict[str, int]:
    """Belt and braces: every row of every table as text, and every bytea column (checkpoints) as bytes."""
    found: dict[str, int] = {}
    async with session_scope() as session:
        tables = (
            await session.scalars(
                sa.text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' "
                    "AND table_type = 'BASE TABLE' ORDER BY table_name"
                )
            )
        ).all()
        byte_columns = (
            await session.execute(
                sa.text(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND data_type = 'bytea'"
                )
            )
        ).all()
        assert {"checkpoint_blobs", "checkpoint_writes", "tool_calls", "execution_nodes"} <= set(tables)
        for secret in needles:
            for table in tables:
                hits = await session.scalar(
                    sa.text(f'SELECT count(*) FROM "{table}" t WHERE strpos(t::text, :s) > 0'), {"s": secret}
                )
                found[table] = found.get(table, 0) + int(hits or 0)
            for table, column in byte_columns:
                hits = await session.scalar(
                    sa.text(
                        f'SELECT count(*) FROM "{table}" WHERE position(convert_to(:s, \'UTF8\') in "{column}") > 0'
                    ),
                    {"s": secret},
                )
                key = f"{table}.{column}"
                found[key] = found.get(key, 0) + int(hits or 0)
    return found


async def test_secrets_never_leak(
    login: Login,
    owner_ctx: AuthContext,
    runners: RunnerFactory,
    jobs_server: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setitem(registry._FACTORIES, ProviderType.openai, FakeLLMProvider)  # no network
    log_start = len(LOG_SINK.chunks)
    api = Recorder(await login("admin@example.com"))
    suffix = uuid.uuid4().hex[:6]

    provider = await api(
        "POST",
        "/llm/providers",
        201,
        json={
            "name": f"Secure OpenAI {suffix}",
            "provider_type": "openai",
            "base_url": "http://127.0.0.1:9/v1",
            "api_key": API_KEY,
            "is_active": True,
        },
    )
    assert provider["api_key"] == {"is_set": True, "hint": "…3456"}
    test = await api("POST", f"/llm/providers/{provider['id']}/test")  # the worker decrypts the key
    assert test["ok"] is True  # the fake adapter answers health checks
    model = await api(
        "POST",
        "/llm/models",
        201,
        json={"provider_id": provider["id"], "model_name": "gpt-secure", "display_name": "Secure model"},
    )

    server = await api(
        "POST",
        "/mcp/servers",
        201,
        json={
            "name": f"Secure jobs {suffix}",
            "slug": f"secure_jobs_{suffix}",
            "transport": "streamable_http",
            "url": jobs_server,
            "headers": {"X-Api-Key": HEADER_SECRET},
            "is_active": True,
        },
    )
    assert server["headers"]["X-Api-Key"]["is_set"] is True
    discovered = await api("POST", f"/mcp/servers/{server['id']}/discover")  # header decrypted + sent
    assert discovered["ok"] is True and "submit_proposal" in discovered["added"]

    pipeline = await api("POST", "/pipelines", 201, json={"name": f"Secure run {suffix}", "graph": _graph(model["id"])})
    execution = await api("POST", f"/pipelines/{pipeline['id']}/run", 202, json={"input": {}})
    assert await runners.new().run(uuid.UUID(execution["id"])) == ExecutionStatus.completed

    # A careless log line that includes both values, after they were decrypted in this process.
    get_logger("security-probe").warning(
        "probe", note=f"key={API_KEY} header={HEADER_SECRET}", authorization=f"Bearer {API_KEY}"
    )

    for path in (
        "/llm/providers",
        "/llm/models",
        "/mcp/servers",
        f"/mcp/servers/{server['id']}",
        f"/mcp/tools?server_id={server['id']}",
        "/secrets",
        "/audit?limit=500",
        "/executions",
        f"/executions/{execution['id']}",
        f"/executions/{execution['id']}/events",
        "/dashboard",
        "/approvals",
        "/pipelines",
    ):
        await api("GET", path)
    detail = await api("GET", f"/executions/{execution['id']}")
    assert detail["execution"]["status"] == "completed"
    assert detail["snapshot"]["llm"]["ask"]["api_key_secret_ref"].startswith("secret:")
    audit = await api("GET", "/audit?event_type=secret.accessed&limit=500")
    purposes = {item["payload"].get("purpose") for item in audit["items"]}
    assert f"llm_provider:Secure OpenAI {suffix}" in purposes
    assert f"mcp_server:secure_jobs_{suffix}" in purposes

    for body in api.bodies:
        for secret in SECRETS:
            assert secret not in body
    leaks = await _scan_db()
    assert leaks == dict.fromkeys(leaks, 0)
    leaks = await _scan_every_table()
    assert leaks == dict.fromkeys(leaks, 0)
    # Positive control: the same scan does see ordinary run data, including inside checkpoint bytes.
    control = await _scan_every_table(("Hello!",))
    assert control["executions"] > 0 and control["checkpoint_writes.blob"] + control["checkpoint_blobs.blob"] > 0
    logs = "".join(LOG_SINK.chunks[log_start:]) + caplog.text
    assert "probe" in logs and "[REDACTED]" in logs
    for secret in SECRETS:
        assert secret not in logs

    await api("DELETE", f"/mcp/servers/{server['id']}")
    await api("DELETE", f"/llm/providers/{provider['id']}")
