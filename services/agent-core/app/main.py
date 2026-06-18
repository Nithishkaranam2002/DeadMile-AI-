"""DeadMile AI — Agent Core (LangGraph + SSE)"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional

import asyncpg
import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from prometheus_client import make_asgi_app
from pydantic import BaseModel, Field

from app.context import clear_stream_context, emit, set_stream_context
from app.graph import build_initial_state, extract_final_response, get_agent_graph
from app.memory import DriverMemory
from app.qdrant_setup import QdrantSeeder
from app.streaming import AgentStreamManager
from app.tracing import AgentTracer
from shared.config import settings

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger(__name__)

stream_manager = AgentStreamManager()
driver_memory = DriverMemory()
tracer = AgentTracer()


class ChatRequest(BaseModel):
    message: str
    driver_id: Optional[str] = None
    session_id: Optional[str] = None
    driver_lat: Optional[float] = None
    driver_lng: Optional[float] = None
    equipment: Optional[str] = None
    max_deadhead: int = Field(default=250, ge=0, le=500)


class MemoryRequest(BaseModel):
    driver_id: str
    preference: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("agent_core_started")
    yield


app = FastAPI(
    title="DeadMile AI — Agent Core",
    description="LangGraph agent with 8 tools for intelligent load optimization",
    version="0.4.0",
    lifespan=lifespan,
)

app.mount("/metrics", make_asgi_app())


async def _run_agent(request: ChatRequest, session_id: str) -> dict[str, Any]:
    set_stream_context(stream_manager, session_id)
    await emit("thinking", {"message": "Understanding your request..."})

    prefs = None
    if request.driver_id:
        prefs = await driver_memory.get_preferences(request.driver_id)
        await emit("thinking", {"message": "Loaded driver preferences from memory"})

    state = build_initial_state(
        message=request.message,
        driver_lat=request.driver_lat,
        driver_lng=request.driver_lng,
        equipment=request.equipment,
        max_deadhead=request.max_deadhead,
        driver_id=request.driver_id,
        driver_preferences=prefs,
        session_id=session_id,
    )

    graph = get_agent_graph()
    config = {"configurable": {"thread_id": session_id}}

    try:
        await emit("thinking", {"message": "Searching loads and calculating profitability..."})
        result = await graph.ainvoke({"messages": state["messages"]}, config=config)
        final_response = await extract_final_response(result)

        if request.driver_id:
            await driver_memory.save_interaction(
                request.driver_id,
                f"Query: {request.message[:200]} | Equipment: {request.equipment}",
            )

        await emit("response", {"text": final_response})
        await emit("done", {
            "response": final_response,
            "session_id": session_id,
        })

        return {
            "response": final_response,
            "session_id": session_id,
        }
    except Exception as exc:
        logger.error("agent_run_failed", error=str(exc))
        err_msg = f"Agent encountered an error: {exc}. Please check service connectivity and API keys."
        await emit("response", {"text": err_msg})
        await emit("done", {"response": err_msg, "error": str(exc), "session_id": session_id})
        return {"response": err_msg, "error": str(exc), "session_id": session_id}
    finally:
        clear_stream_context()


@app.get("/health")
async def health() -> dict[str, Any]:
    import os

    checks: dict[str, Any] = {"service": "agent-core", "status": "healthy"}
    try:
        from qdrant_client import QdrantClient

        QdrantClient(
            host=os.getenv("QDRANT_HOST", "qdrant"),
            port=int(os.getenv("QDRANT_PORT", "6333")),
        ).get_collections()
        checks["qdrant"] = "ok"
    except Exception as exc:
        checks["qdrant"] = f"unreachable: {exc}"
    return checks


@app.get("/")
async def root() -> dict[str, list[str]]:
    return {
        "tools": [
            "search_loads",
            "calculate_profitability",
            "get_market_score",
            "predict_lane_rate",
            "find_load_chain",
            "get_fuel_prices",
            "semantic_load_search",
            "get_driver_preferences",
        ]
    }


@app.post("/chat")
async def chat(request: ChatRequest) -> dict[str, Any]:
    session_id = request.session_id or str(uuid.uuid4())
    await stream_manager.create_stream(session_id)
    return await _run_agent(request, session_id)


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    session_id = request.session_id or str(uuid.uuid4())
    await stream_manager.create_stream(session_id)

    async def run_and_stream() -> None:
        await _run_agent(request, session_id)

    asyncio.create_task(run_and_stream())
    return StreamingResponse(
        stream_manager.stream_response(session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/memory/save")
async def save_preference(request: MemoryRequest) -> dict[str, str]:
    await driver_memory.save_preference(request.driver_id, request.preference)
    return {"status": "saved", "driver_id": request.driver_id}


@app.get("/memory/{driver_id}")
async def get_preferences(driver_id: str) -> dict:
    return await driver_memory.get_preferences(driver_id)


@app.post("/seed-vectors")
async def seed_qdrant() -> dict[str, Any]:
    pool = await asyncpg.create_pool(dsn=settings.asyncpg_dsn, min_size=1, max_size=3)
    try:
        seeder = QdrantSeeder()
        count = await seeder.seed(pool)
        return {"status": "ok", "vectors_seeded": count}
    finally:
        await pool.close()
