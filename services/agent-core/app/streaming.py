"""Server-Sent Events streaming for agent responses."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator, Optional


class AgentStreamManager:
    """Manages SSE streams keyed by session_id."""

    def __init__(self) -> None:
        self.active_streams: dict[str, asyncio.Queue] = {}

    async def create_stream(self, session_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self.active_streams[session_id] = queue
        return queue

    async def emit(self, session_id: str, event_type: str, data: dict[str, Any]) -> None:
        if session_id in self.active_streams:
            await self.active_streams[session_id].put({"event": event_type, "data": data})

    async def stream_response(self, session_id: str) -> AsyncGenerator[str, None]:
        queue = self.active_streams.get(session_id)
        if not queue:
            yield f"event: error\ndata: {json.dumps({'message': 'Stream not found'})}\n\n"
            return

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=120.0)
            except asyncio.TimeoutError:
                yield f"event: error\ndata: {json.dumps({'message': 'Stream timeout'})}\n\n"
                break

            payload = json.dumps(event["data"], default=str)
            if event["event"] == "done":
                yield f"event: done\ndata: {payload}\n\n"
                break
            yield f"event: {event['event']}\ndata: {payload}\n\n"

        self.active_streams.pop(session_id, None)

    def has_stream(self, session_id: str) -> bool:
        return session_id in self.active_streams
