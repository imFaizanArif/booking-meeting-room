from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx
import pytest

from app.main import app

pytestmark = pytest.mark.integration

PASSWORDS = {
    "admin@example.com": "admin-password",
    "operator@example.com": "operator-password",
    "viewer@example.com": "viewer-password",
}
Login = Callable[[str], Awaitable[httpx.AsyncClient]]


@pytest.fixture(autouse=True)
async def _clean(clean_runtime: dict[str, Any]) -> dict[str, Any]:
    return clean_runtime


def new_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


async def login_client(email: str, password: str | None = None) -> httpx.AsyncClient:
    """A client with the session cookie and the CSRF header set, like the web app."""
    client = new_client()
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password or PASSWORDS[email]})
    assert response.status_code == 200, response.text
    client.headers["x-csrf-token"] = response.json()["csrf_token"]
    return client


@pytest.fixture
async def login() -> AsyncIterator[Login]:
    clients: list[httpx.AsyncClient] = []

    async def make(email: str) -> httpx.AsyncClient:
        client = await login_client(email)
        clients.append(client)
        return client

    yield make
    for client in clients:
        await client.aclose()


@pytest.fixture
async def anon() -> AsyncIterator[httpx.AsyncClient]:
    async with new_client() as client:
        yield client


def assert_envelope(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    error = body["error"]
    assert set(error) == {"code", "message", "request_id", "details"}
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]
    assert error["request_id"] == response.headers["x-request-id"]
    assert isinstance(error["details"], dict)
    return error
