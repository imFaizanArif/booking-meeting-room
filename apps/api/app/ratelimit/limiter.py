"""Rate limits and concurrency caps backed by Redis.

`TokenBucket` is a single Lua script so check-and-take is atomic across processes. Keys
are namespaced per scope: `rl:provider:<id>`, `rl:mcp:<id>`, `rl:ws:<id>`, `rl:login:<ip>`.
`ConcurrencyLimiter` uses a sorted set of lease ids with expiry so a crashed holder frees
its slot automatically.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol

from redis.asyncio import Redis

from app.core.errors import RateLimited

_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_per_ms = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1]) or capacity
local ts = tonumber(data[2]) or now
tokens = math.min(capacity, tokens + (now - ts) * refill_per_ms)
local allowed = 0
local wait = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
else
  wait = math.ceil((cost - tokens) / refill_per_ms)
end
redis.call('HSET', key, 'tokens', tokens, 'ts', now)
redis.call('PEXPIRE', key, math.ceil(capacity / refill_per_ms) + 1000)
return {allowed, wait}
"""


@dataclass(frozen=True)
class Limit:
    requests: int
    per_seconds: int


class RateLimiter(Protocol):
    async def acquire(self, key: str, limit: Limit, *, wait: bool = True, max_wait_s: float = 30.0) -> None: ...


class TokenBucket:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._script = redis.register_script(_BUCKET_LUA)

    async def try_take(self, key: str, limit: Limit, cost: int = 1) -> tuple[bool, int]:
        refill_per_ms = limit.requests / (limit.per_seconds * 1000)
        allowed, wait_ms = await self._script(
            keys=[f"rl:{key}"], args=[limit.requests, refill_per_ms, int(time.time() * 1000), cost]
        )
        return bool(allowed), int(wait_ms)

    async def acquire(self, key: str, limit: Limit, *, wait: bool = True, max_wait_s: float = 30.0) -> None:
        deadline = time.monotonic() + max_wait_s
        while True:
            allowed, wait_ms = await self.try_take(key, limit)
            if allowed:
                return
            if not wait or time.monotonic() + wait_ms / 1000 > deadline:
                raise RateLimited(
                    "Rate limit exceeded", details={"key": key, "retry_after_ms": wait_ms}
                )
            await asyncio.sleep(wait_ms / 1000)


class ConcurrencyLimiter:
    def __init__(self, redis: Redis, lease_s: int = 600) -> None:
        self._redis = redis
        self._lease_s = lease_s

    @asynccontextmanager
    async def slot(self, key: str, max_concurrent: int, *, max_wait_s: float = 60.0) -> AsyncIterator[None]:
        zkey = f"cc:{key}"
        token = uuid.uuid4().hex
        deadline = time.monotonic() + max_wait_s
        while True:
            now = time.time()
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(zkey, 0, now)
                pipe.zcard(zkey)
                _, count = await pipe.execute()
            if count < max_concurrent:
                # Lower scores were added earlier; a rank below the cap wins the slot.
                await self._redis.zadd(zkey, {token: now + self._lease_s})
                rank = await self._redis.zrank(zkey, token)
                if rank is not None and rank < max_concurrent:
                    break
                await self._redis.zrem(zkey, token)
            if time.monotonic() > deadline:
                raise RateLimited("Concurrency limit reached", details={"key": key, "limit": max_concurrent})
            await asyncio.sleep(0.2)
        try:
            yield
        finally:
            await self._redis.zrem(zkey, token)
