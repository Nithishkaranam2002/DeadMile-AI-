"""Redis caching utilities."""

from __future__ import annotations

import json
from typing import Any, Optional

import redis.asyncio as aioredis


class CacheManager:
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        if self._client is None:
            self._client = aioredis.from_url(self._redis_url, decode_responses=True)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    @property
    def redis(self) -> aioredis.Redis:
        if self._client is None:
            raise RuntimeError("CacheManager not connected")
        return self._client

    async def get(self, key: str) -> Optional[dict[str, Any]]:
        await self.connect()
        val = await self.redis.get(key)
        return json.loads(val) if val else None

    async def set(self, key: str, value: dict[str, Any], ttl: int = 3600) -> None:
        await self.connect()
        await self.redis.set(key, json.dumps(value), ex=ttl)

    async def invalidate(self, pattern: str) -> int:
        await self.connect()
        keys = [k async for k in self.redis.scan_iter(match=pattern)]
        if keys:
            return await self.redis.delete(*keys)
        return 0
