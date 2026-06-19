"""Agent recommendation proxy."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.config import settings
from app.proxy import proxy_json, proxy_sse
from app.schemas import RecommendRequest

router = APIRouter(prefix="/recommend", tags=["recommend"])


@router.post("")
async def recommend_loads(request: RecommendRequest, req: Request) -> dict:
    """Proxy to agent-core /chat."""
    request_id = req.headers.get("X-Request-ID")
    return await proxy_json(
        "POST",
        f"{settings.agent_core_url}/chat",
        json_body=request.model_dump(),
        timeout=60.0,
        request_id=request_id,
    )


@router.post("/stream")
async def recommend_stream(request: RecommendRequest, req: Request):
    """SSE proxy to agent-core /chat/stream."""
    request_id = req.headers.get("X-Request-ID")
    return await proxy_sse(
        f"{settings.agent_core_url}/chat/stream",
        request.model_dump(),
        timeout=120.0,
        request_id=request_id,
    )
