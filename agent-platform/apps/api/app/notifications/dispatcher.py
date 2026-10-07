"""NotificationDispatcher with webhook, Slack-compatible and Discord-compatible notifiers.

Rules: never include secrets (payloads are redacted), never include one-click approve links
(only a link to the approval page), retry with backoff without blocking executions (the
approval path sends from a background job).
"""

from __future__ import annotations

import asyncio
import json
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
from sqlalchemy import select

from app.core.config import get_settings
from app.core.enums import NotificationChannelType
from app.core.logging import get_logger
from app.core.redaction import redactor
from app.core.security import sign_payload
from app.core.ssrf import guard_url
from app.core.time import utcnow
from app.db.session import session_scope
from app.models import Approval, Execution, NotificationChannel
from app.secrets.manager import get_secret_manager

log = get_logger(__name__)


@dataclass
class NotificationMessage:
    event: str
    title: str
    text: str
    fields: dict[str, Any] = field(default_factory=dict)
    url: str | None = None


class Notifier(Protocol):
    async def send(self, url: str, message: NotificationMessage, signing_secret: str | None) -> None: ...


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0), follow_redirects=False)


class WebhookNotifier:
    async def send(self, url: str, message: NotificationMessage, signing_secret: str | None) -> None:
        body = json.dumps(
            {
                "event": message.event,
                "title": message.title,
                "text": message.text,
                "fields": message.fields,
                "url": message.url,
                "sent_at": utcnow().isoformat(),
            },
            default=str,
        ).encode()
        headers = {"content-type": "application/json"}
        if signing_secret:
            headers["x-agent-platform-signature"] = sign_payload(signing_secret, body, int(time.time()))
        async with _client() as client:
            response = await client.post(url, content=body, headers=headers)
            response.raise_for_status()


class SlackNotifier:
    async def send(self, url: str, message: NotificationMessage, signing_secret: str | None) -> None:
        lines = [f"*{message.title}*", message.text]
        lines += [f"• {k}: `{v}`" for k, v in message.fields.items()]
        if message.url:
            lines.append(f"<{message.url}|Open in Agent Platform>")
        async with _client() as client:
            response = await client.post(url, json={"text": "\n".join(lines)})
            response.raise_for_status()


class DiscordNotifier:
    async def send(self, url: str, message: NotificationMessage, signing_secret: str | None) -> None:
        lines = [f"**{message.title}**", message.text]
        lines += [f"- {k}: `{v}`" for k, v in message.fields.items()]
        if message.url:
            lines.append(message.url)
        async with _client() as client:
            response = await client.post(url, json={"content": "\n".join(lines)[:1900]})
            response.raise_for_status()


NOTIFIERS: dict[NotificationChannelType, Notifier] = {
    NotificationChannelType.webhook: WebhookNotifier(),
    NotificationChannelType.slack: SlackNotifier(),
    NotificationChannelType.discord: DiscordNotifier(),
}


class NotificationDispatcher:
    def __init__(self, notifiers: dict[NotificationChannelType, Notifier] | None = None, attempts: int = 4) -> None:
        self.notifiers = notifiers or NOTIFIERS
        self.attempts = attempts

    async def send_to_channel(self, channel: NotificationChannel, message: NotificationMessage) -> bool:
        async with session_scope() as session:
            manager = get_secret_manager()
            url = await manager.get(session, channel.workspace_id, channel.url_secret_ref)
            signing = (
                await manager.get(session, channel.workspace_id, channel.signing_secret_ref)
                if channel.signing_secret_ref
                else None
            )
        clean = NotificationMessage(
            event=message.event,
            title=redactor.redact_text(message.title),
            text=redactor.redact_text(message.text),
            fields=redactor.redact(message.fields),
            url=message.url,
        )
        notifier = self.notifiers[channel.channel_type]
        ok = False
        for attempt in range(self.attempts):
            try:
                await guard_url(url)
                await notifier.send(url, clean, signing)
                ok = True
                break
            except Exception as exc:
                log.warning(
                    "notification_failed",
                    channel=channel.name,
                    attempt=attempt + 1,
                    error=redactor.redact_text(str(exc))[:300],
                )
                if attempt + 1 < self.attempts:
                    await asyncio.sleep(min(30.0, 2**attempt) + random.uniform(0, 0.5))
        async with session_scope() as session:
            row = await session.get(NotificationChannel, channel.id)
            if row is not None:
                row.last_delivery_ok = ok
                row.last_delivery_at = utcnow()
        return ok

    async def send(
        self, workspace_id: uuid.UUID, message: NotificationMessage, channel_ids: list[uuid.UUID] | None = None
    ) -> dict[str, bool]:
        async with session_scope() as session:
            query = select(NotificationChannel).where(
                NotificationChannel.workspace_id == workspace_id, NotificationChannel.is_active.is_(True)
            )
            if channel_ids:
                query = query.where(NotificationChannel.id.in_(channel_ids))
            channels = list((await session.scalars(query)).all())
        if not channel_ids:
            channels = [c for c in channels if not c.events or message.event in c.events]
        results = await asyncio.gather(*(self.send_to_channel(c, message) for c in channels))
        return {c.name: ok for c, ok in zip(channels, results, strict=True)}

    async def notify_approval(self, approval_id: uuid.UUID) -> dict[str, bool]:
        async with session_scope() as session:
            approval = await session.get(Approval, approval_id)
            if approval is None:
                return {}
            execution = await session.get(Execution, approval.execution_id)
            pipeline = (execution.config_snapshot or {}).get("pipeline_name") if execution else None
        args = approval.original_arguments or {}
        preview = {k: (str(v)[:120] + "…" if len(str(v)) > 120 else v) for k, v in list(args.items())[:8]}
        message = NotificationMessage(
            event="approval.created",
            title=f"Approval needed: {approval.title}",
            text=approval.summary or "An execution is paused and waiting for a decision.",
            fields={
                "execution": str(approval.execution_id),
                "pipeline": pipeline or "-",
                "risk": approval.risk_level or "-",
                **{f"arg.{k}": v for k, v in preview.items()},
            },
            url=f"{get_settings().public_web_url.rstrip('/')}/approvals/{approval.id}",
        )
        return await self.send(approval.workspace_id, message)
