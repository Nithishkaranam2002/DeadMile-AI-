"""DeadMile AI — Agent Core (LangGraph)"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from prometheus_client import make_asgi_app


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield


app = FastAPI(
    title="DeadMile AI — Agent Core",
    description="LangGraph agent with 8 tools for intelligent load optimization",
    version="0.1.0",
    lifespan=lifespan,
)

app.mount("/metrics", make_asgi_app())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "agent-core"}


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "DeadMile AI Agent Core",
        "tools": [
            "search_loads",
            "calculate_profitability",
            "get_market_score",
            "predict_lane_rate",
            "find_load_chain",
            "get_fuel_prices",
            "semantic_load_search",
            "get_driver_preferences",
        ],
    }
