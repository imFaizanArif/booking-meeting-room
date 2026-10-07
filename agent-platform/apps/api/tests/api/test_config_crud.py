"""Config writes that flush twice (insert, then secret ref / update) must return 2xx, not 500.

Regression: `updated_at` (onupdate=now()) was expired by the second flush and lazily loaded
while building the response, raising MissingGreenlet.
"""

from __future__ import annotations

import uuid

from tests.api.conftest import Login

V1 = "/api/v1"


async def test_provider_and_server_writes(login: Login, jobs_server: str) -> None:
    client = await login("admin@example.com")
    suffix = uuid.uuid4().hex[:6]

    created = await client.post(f"{V1}/llm/providers", json={
        "name": f"Keyed {suffix}", "provider_type": "openai", "api_key": "sk-regression-key-0001"})
    assert created.status_code == 201, created.text
    provider = created.json()
    assert provider["api_key"] == {"is_set": True, "hint": "…0001"}
    patched = await client.patch(f"{V1}/llm/providers/{provider['id']}", json={"name": f"Renamed {suffix}"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["updated_at"] >= provider["updated_at"]
    cleared = await client.patch(f"{V1}/llm/providers/{provider['id']}", json={"clear_api_key": True})
    assert cleared.status_code == 200 and cleared.json()["api_key"]["is_set"] is False

    server_in = {"name": f"Remote {suffix}", "slug": f"remote_{suffix}", "transport": "streamable_http",
                 "url": jobs_server, "headers": {"Authorization": "Bearer regression-token"}}
    created = await client.post(f"{V1}/mcp/servers", json=server_in)
    assert created.status_code == 201, created.text
    server = created.json()
    assert server["headers"]["Authorization"]["is_set"] is True
    updated = await client.put(f"{V1}/mcp/servers/{server['id']}",
                               json={**server_in, "headers": {}, "headers_keep": ["Authorization"],
                                     "name": f"Remote 2 {suffix}"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["headers"]["Authorization"]["is_set"] is True

    assert (await client.delete(f"{V1}/mcp/servers/{server['id']}")).status_code == 200
    assert (await client.delete(f"{V1}/llm/providers/{provider['id']}")).status_code == 200


async def test_operator_cannot_create_stdio_server(login: Login) -> None:
    client = await login("operator@example.com")
    response = await client.post(f"{V1}/mcp/servers", json={
        "name": "local", "transport": "stdio", "command": "/bin/sh", "args": ["-c", "id"], "is_active": True,
        "confirm_command": True})
    assert response.status_code == 403
    assert response.json()["error"]["details"] == {"required_role": "owner"}
