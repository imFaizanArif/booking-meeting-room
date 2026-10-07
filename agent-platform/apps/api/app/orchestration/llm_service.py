"""LLM calls on behalf of a node: provider resolution, rate limits, usage and events."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import sqlalchemy as sa

from app.audit.writer import audit
from app.core.enums import AuditEventType, EventType
from app.db.session import session_scope
from app.events.publisher import publish_execution_event
from app.llm.base import LLMProvider, ProviderConfig
from app.llm.registry import KEYLESS, build_provider, estimate_cost
from app.llm.types import LLMRequest, LLMResponse
from app.models import Execution, LLMUsage
from app.orchestration.snapshot import ConfigSnapshot, SnapshotLLM
from app.ratelimit.limiter import ConcurrencyLimiter, Limit, TokenBucket
from app.secrets.manager import get_secret_manager
from app.services.context import WORKER_ACTOR


class LLMService:
    def __init__(
        self,
        *,
        execution_id: uuid.UUID,
        workspace_id: uuid.UUID,
        snapshot: ConfigSnapshot,
        bucket: TokenBucket | None = None,
        concurrency: ConcurrencyLimiter | None = None,
        timeout_s: float = 120.0,
    ) -> None:
        self.execution_id = execution_id
        self.workspace_id = workspace_id
        self.snapshot = snapshot
        self._providers: dict[uuid.UUID, LLMProvider] = {}
        self._bucket = bucket
        self._concurrency = concurrency
        self._timeout_s = timeout_s

    async def _provider(self, snap: SnapshotLLM) -> LLMProvider:
        cached = self._providers.get(snap.provider_id)
        if cached is not None:
            return cached
        api_key: str | None = None
        if snap.api_key_secret_ref and snap.provider_type not in KEYLESS:
            async with session_scope() as session:
                api_key = await get_secret_manager().get(session, self.workspace_id, snap.api_key_secret_ref)
                await audit(
                    session,
                    event_type=AuditEventType.secret_accessed,
                    actor=WORKER_ACTOR,
                    workspace_id=self.workspace_id,
                    entity_type="secret",
                    entity_id=snap.api_key_secret_ref,
                    execution_id=self.execution_id,
                    payload={"purpose": f"llm_provider:{snap.provider_name}"},
                )
        provider = build_provider(
            ProviderConfig(
                provider_type=snap.provider_type.value,
                base_url=snap.base_url,
                api_key=api_key,
                timeout_s=self._timeout_s,
                metadata=snap.provider_metadata,
            )
        )
        self._providers[snap.provider_id] = provider
        return provider

    def config_for(self, node_id: str) -> SnapshotLLM:
        return self.snapshot.llm[node_id]

    async def generate(self, node_id: str, request: LLMRequest, *, summary_hint: str | None = None) -> LLMResponse:
        snap = self.config_for(node_id)
        provider = await self._provider(snap)
        await publish_execution_event(
            workspace_id=self.workspace_id,
            execution_id=self.execution_id,
            type=EventType.llm_requested,
            node_id=node_id,
            payload={
                "provider": snap.provider_type.value,
                "model": snap.model_name,
                "messages": len(request.messages),
                "tools": len(request.tools),
            },
        )
        if self._bucket is not None and snap.requests_per_minute:
            await self._bucket.acquire(f"provider:{snap.provider_id}", Limit(snap.requests_per_minute, 60))
        if self._concurrency is not None and snap.max_concurrency:
            async with self._concurrency.slot(f"provider:{snap.provider_id}", snap.max_concurrency):
                response = await provider.generate(request)
        else:
            response = await provider.generate(request)
        cost = estimate_cost(response.usage, snap.input_price_per_mtok, snap.output_price_per_mtok)
        await self._record_usage(node_id, snap, response, cost)
        await publish_execution_event(
            workspace_id=self.workspace_id,
            execution_id=self.execution_id,
            type=EventType.llm_completed,
            node_id=node_id,
            payload={
                "provider": snap.provider_type.value,
                "model": snap.model_name,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "estimated_cost": str(cost),
                "latency_ms": response.latency_ms,
                "stop_reason": response.stop_reason.value,
                "tool_calls": [c.name for c in response.message.tool_calls],
                "summary": _summary(response),
            },
        )
        return response

    async def _record_usage(self, node_id: str, snap: SnapshotLLM, response: LLMResponse, cost: Decimal) -> None:
        async with session_scope() as session:
            session.add(
                LLMUsage(
                    workspace_id=self.workspace_id,
                    execution_id=self.execution_id,
                    node_id=node_id,
                    provider_id=snap.provider_id,
                    provider=snap.provider_type.value,
                    model=snap.model_name,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    total_tokens=response.usage.total_tokens,
                    estimated_cost=cost,
                    latency_ms=response.latency_ms,
                    stop_reason=response.stop_reason.value,
                    summary=_summary(response),
                )
            )
            await session.execute(
                sa.update(Execution)
                .where(Execution.id == self.execution_id)
                .values(
                    total_tokens=Execution.total_tokens + response.usage.total_tokens,
                    estimated_cost=Execution.estimated_cost + cost,
                )
            )


def _summary(response: LLMResponse) -> str:
    """A short description of the output. Never the model's reasoning."""
    parts: list[Any] = []
    if response.message.content:
        text = response.message.content.strip().replace("\n", " ")
        parts.append(text[:240] + ("…" if len(text) > 240 else ""))
    if response.message.tool_calls:
        parts.append("calls: " + ", ".join(c.name for c in response.message.tool_calls))
    return " | ".join(parts) or "(empty)"
