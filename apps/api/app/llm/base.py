"""The provider protocol plus shared HTTP plumbing for adapters."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.llm import errors
from app.llm.types import LLMRequest, LLMResponse, LLMStreamEvent


@dataclass(frozen=True)
class ProviderConfig:
    """Resolved provider settings handed to an adapter (secret already decrypted)."""

    provider_type: str
    base_url: str | None
    api_key: str | None = None
    timeout_s: float = 120.0
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    async def generate(self, req: LLMRequest) -> LLMResponse: ...
    def stream(self, req: LLMRequest) -> AsyncIterator[LLMStreamEvent]: ...
    async def health(self, model: str | None = None) -> str: ...


class HttpAdapter:
    """Base for adapters that call an HTTP API with httpx."""

    provider_name = "http"
    default_base_url = ""

    def __init__(self, config: ProviderConfig, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.config = config
        self._transport = transport

    @property
    def base_url(self) -> str:
        return (self.config.base_url or self.default_base_url).rstrip("/")

    def headers(self) -> dict[str, str]:
        return {"content-type": "application/json"}

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers(),
            timeout=httpx.Timeout(self.config.timeout_s, connect=10.0),
            transport=self._transport,
        )

    def error_message(self, response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return response.text[:300]
        err = body.get("error") if isinstance(body, dict) else None
        if isinstance(err, dict):
            return str(err.get("message") or err)[:300]
        return str(err or body)[:300]

    def classify(self, response: httpx.Response) -> errors.LLMError:
        message = self.error_message(response)
        lowered = message.lower()
        # Providers signal these via typed error codes inside 400 bodies.
        if response.status_code == 400 and (
            "context_length" in lowered or "too long" in lowered or "maximum context" in lowered
        ):
            return errors.ContextTooLong(message, details={"provider": self.provider_name})
        if response.status_code == 400 and "content_filter" in lowered:
            return errors.ContentFiltered(message, details={"provider": self.provider_name})
        return errors.from_http_status(response.status_code, message, provider=self.provider_name)

    async def post_json(self, path: str, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        started = time.perf_counter()
        try:
            async with self.client() as client:
                response = await client.post(path, json=payload)
        except httpx.TimeoutException as exc:
            raise errors.TimeoutError_(
                f"{self.provider_name} request timed out", details={"provider": self.provider_name}
            ) from exc
        except httpx.TransportError as exc:
            raise errors.ProviderUnavailable(
                f"{self.provider_name} is unreachable: {exc.__class__.__name__}",
                details={"provider": self.provider_name},
            ) from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            raise self.classify(response)
        return response.json(), latency_ms

    async def stream(self, req: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        """Default streaming: one generate call surfaced as stream events.

        Adapters with native streaming override this. The orchestrator uses `generate`;
        streaming exists for interactive surfaces.
        """
        response = await self.generate(req)  # type: ignore[attr-defined]
        if response.message.content:
            yield LLMStreamEvent(type="text_delta", text=response.message.content)
        for call in response.message.tool_calls:
            yield LLMStreamEvent(type="tool_call", tool_call=call)
        yield LLMStreamEvent(type="done", response=response)
