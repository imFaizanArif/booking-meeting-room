"""EventBus interface with a Redis pub/sub implementation.

Pub/sub is a delivery optimisation; the durable record is `execution_events`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Protocol

from redis.asyncio import Redis

from app.core.redis import get_redis


class EventBus(Protocol):
    async def publish(self, channel: str, message: dict[str, Any]) -> None: ...
    def subscribe(self, *channels: str) -> AsyncIterator[dict[str, Any]]: ...


class RedisEventBus:
    def __init__(self, redis: Redis | None = None) -> None:
        self._redis = redis

    @property
    def redis(self) -> Redis:
        return self._redis or get_redis()

    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        await self.redis.publish(channel, json.dumps(message, default=str))

    async def subscribe(self, *channels: str) -> AsyncIterator[dict[str, Any]]:
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(*channels)
        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
                if msg is None:
                    yield {"type": "__heartbeat__"}
                    continue
                try:
                    yield json.loads(msg["data"])
                except (TypeError, json.JSONDecodeError):
                    continue
        finally:
            await pubsub.unsubscribe(*channels)
            await pubsub.aclose()


_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = RedisEventBus()
    return _bus


def set_event_bus(bus: EventBus) -> None:
    global _bus
    _bus = bus
