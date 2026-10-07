"""EventBus interface with a Redis pub/sub implementation.

Pub/sub is a delivery optimisation; the durable record is `execution_events`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any, Protocol

from redis.asyncio import Redis

from app.core.redis import get_redis

# Control messages a subscription yields besides published ones.
SUBSCRIBED = "__subscribed__"  # always first: the subscription is live from here on
HEARTBEAT = "__heartbeat__"  # nothing arrived for a while


class EventBus(Protocol):
    async def publish(self, channel: str, message: dict[str, Any]) -> None: ...

    def subscribe(self, *channels: str) -> AsyncGenerator[dict[str, Any]]:
        """Yields `{"type": SUBSCRIBED}` once every channel is subscribed, then messages and heartbeats.

        Anything published after the SUBSCRIBED message has been received is delivered, which is
        what lets a consumer replay persisted history afterwards without a gap.
        """
        ...


class RedisEventBus:
    def __init__(self, redis: Redis | None = None) -> None:
        self._redis = redis

    @property
    def redis(self) -> Redis:
        return self._redis or get_redis()

    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        await self.redis.publish(channel, json.dumps(message, default=str))

    async def subscribe(self, *channels: str) -> AsyncGenerator[dict[str, Any]]:
        pubsub = self.redis.pubsub()
        try:
            await pubsub.subscribe(*channels)
            # SUBSCRIBE only sends the command; the server's confirmations prove it is in effect.
            # Replies on one connection are ordered, so no published message can precede them.
            confirmed = 0
            while confirmed < len(set(channels)):
                msg = await pubsub.get_message(timeout=10.0)
                if msg is None:
                    raise ConnectionError(f"Redis did not confirm the subscription to {channels}")
                if msg["type"] == "subscribe":
                    confirmed += 1
            yield {"type": SUBSCRIBED}
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
                if msg is None:
                    yield {"type": HEARTBEAT}
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
