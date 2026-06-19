"""HTTP proxy helpers for inter-service calls."""

from __future__ import annotations

import uuid
from typing import Any, AsyncIterator, Optional

import httpx
from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse


def request_id_header(existing: Optional[str] = None) -> dict[str, str]:
    return {"X-Request-ID": existing or str(uuid.uuid4())}


async def proxy_json(
    method: str,
    url: str,
    *,
    params: Optional[dict] = None,
    json_body: Optional[dict] = None,
    timeout: float = 60.0,
    request_id: Optional[str] = None,
) -> Any:
    headers = request_id_header(request_id)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.request(method, url, params=params, json=json_body, headers=headers)
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


async def proxy_sse(
    url: str,
    json_body: dict,
    *,
    timeout: float = 120.0,
    request_id: Optional[str] = None,
) -> StreamingResponse:
    headers = {**request_id_header(request_id), "Accept": "text/event-stream"}

    async def event_generator() -> AsyncIterator[bytes]:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, json=json_body, headers=headers) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    yield f"event: error\ndata: {body.decode()}\n\n".encode()
                    return
                async for line in resp.aiter_lines():
                    if line:
                        yield f"{line}\n".encode()
                    else:
                        yield b"\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


async def check_health(url: str, timeout: float = 5.0) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            return {"status": "healthy" if resp.status_code == 200 else "unhealthy", "code": resp.status_code}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}
