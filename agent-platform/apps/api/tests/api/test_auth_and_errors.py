"""Auth, CSRF, roles and the error envelope."""

from __future__ import annotations

import uuid

import httpx

from tests.api.conftest import Login, assert_envelope, new_client
from tests.helpers import demo_pipeline_id

V1 = "/api/v1"


async def test_login_me_logout(anon: httpx.AsyncClient) -> None:
    response = await anon.post(f"{V1}/auth/login", json={"email": "operator@example.com",
                                                          "password": "operator-password"})
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "operator@example.com" and body["role"] == "operator"
    assert body["csrf_token"] == response.cookies["ap_csrf"]
    set_cookie = response.headers.get_list("set-cookie")
    assert any(c.startswith("ap_session=") and "HttpOnly" in c for c in set_cookie)
    assert not any(c.startswith("ap_csrf=") and "HttpOnly" in c for c in set_cookie)

    me = await anon.get(f"{V1}/auth/me")
    assert me.status_code == 200 and me.json()["email"] == "operator@example.com"
    assert me.json()["csrf_token"] is None

    out = await anon.post(f"{V1}/auth/logout", headers={"x-csrf-token": body["csrf_token"]})
    assert out.status_code == 200 and out.json() == {"ok": True}
    assert_envelope(await anon.get(f"{V1}/auth/me"), 401, "UNAUTHENTICATED")


async def test_revoked_session_cookie_is_rejected() -> None:
    async with new_client() as client:
        login = await client.post(f"{V1}/auth/login", json={"email": "viewer@example.com",
                                                             "password": "viewer-password"})
        token = login.cookies["ap_session"]
        await client.post(f"{V1}/auth/logout", headers={"x-csrf-token": login.json()["csrf_token"]})
    async with new_client() as replay:
        replay.cookies.set("ap_session", token)
        assert_envelope(await replay.get(f"{V1}/auth/me"), 401, "UNAUTHENTICATED")


async def test_bad_credentials(anon: httpx.AsyncClient) -> None:
    error = assert_envelope(await anon.post(f"{V1}/auth/login", json={"email": "operator@example.com",
                                                                       "password": "nope"}),
                            401, "INVALID_CREDENTIALS")
    assert "password" in error["message"].lower()
    assert_envelope(await anon.post(f"{V1}/auth/login", json={"email": "ghost@example.com", "password": "x"}),
                    401, "INVALID_CREDENTIALS")


async def test_unauthenticated_requests_get_401(anon: httpx.AsyncClient) -> None:
    for method, path in (("GET", "/pipelines"), ("GET", "/executions"), ("GET", "/approvals"),
                         ("POST", "/pipelines"), ("GET", "/llm/providers")):
        assert_envelope(await anon.request(method, f"{V1}{path}", json={}), 401, "UNAUTHENTICATED")


async def test_missing_or_wrong_csrf_is_403(login: Login) -> None:
    client = await login("operator@example.com")
    body = {"name": f"csrf-{uuid.uuid4().hex[:6]}"}
    good = client.headers.pop("x-csrf-token")
    assert_envelope(await client.post(f"{V1}/pipelines", json=body), 403, "CSRF_FAILED")
    assert_envelope(await client.post(f"{V1}/pipelines", json=body, headers={"x-csrf-token": "forged"}),
                    403, "CSRF_FAILED")
    # Safe methods do not need it.
    assert (await client.get(f"{V1}/pipelines")).status_code == 200
    created = await client.post(f"{V1}/pipelines", json=body, headers={"x-csrf-token": good})
    assert created.status_code == 201


async def test_viewer_cannot_mutate(login: Login) -> None:
    viewer = await login("viewer@example.com")
    assert (await viewer.get(f"{V1}/pipelines")).status_code == 200
    error = assert_envelope(await viewer.post(f"{V1}/pipelines", json={"name": "viewer pipeline"}),
                            403, "FORBIDDEN")
    assert error["details"] == {"required_role": "operator"}
    pid = await demo_pipeline_id()
    assert_envelope(await viewer.post(f"{V1}/pipelines/{pid}/run", json={"input": {}}), 403, "FORBIDDEN")
    assert_envelope(await viewer.post(f"{V1}/approvals/{uuid.uuid4()}/decision", json={"action": "approve"}),
                    403, "FORBIDDEN")
    assert_envelope(await viewer.post(f"{V1}/llm/providers", json={"name": "x", "provider_type": "fake"}),
                    403, "FORBIDDEN")


async def test_error_envelope_shapes(login: Login) -> None:
    client = await login("operator@example.com")
    missing = assert_envelope(await client.get(f"{V1}/pipelines/{uuid.uuid4()}"), 404, "NOT_FOUND")
    assert missing["details"] == {}
    assert_envelope(await client.get(f"{V1}/executions/{uuid.uuid4()}"), 404, "NOT_FOUND")
    assert_envelope(await client.get(f"{V1}/no-such-route"), 404, "NOT_FOUND")

    invalid = assert_envelope(await client.post(f"{V1}/pipelines", json={"name": ""}), 422, "VALIDATION_ERROR")
    assert invalid["details"]["fields"][0]["field"] == "name"
    assert_envelope(await client.get(f"{V1}/pipelines/not-a-uuid"), 422, "VALIDATION_ERROR")
    bad_graph = await client.post(f"{V1}/pipelines/{await demo_pipeline_id()}/versions",
                                  json={"graph": {"nodes": [], "edges": []}})
    issues = assert_envelope(bad_graph, 422, "VALIDATION_ERROR")["details"]["issues"]
    assert any("Trigger" in i["message"] for i in issues)

    name = f"dup-{uuid.uuid4().hex[:6]}"
    assert (await client.post(f"{V1}/pipelines", json={"name": name})).status_code == 201
    assert_envelope(await client.post(f"{V1}/pipelines", json={"name": name}), 409, "CONFLICT")


async def test_request_id_is_echoed(login: Login) -> None:
    client = await login("viewer@example.com")
    response = await client.get(f"{V1}/pipelines/{uuid.uuid4()}", headers={"x-request-id": "req-abc-123"})
    assert response.headers["x-request-id"] == "req-abc-123"
    assert response.json()["error"]["request_id"] == "req-abc-123"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
