"""DeadMile AI — API Gateway"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from prometheus_client import generate_latest
from starlette.responses import Response

from app.config import settings
from app.db import close_pool, get_pool
from app.middleware.auth import ApiKeyMiddleware
from app.middleware.cors import setup_cors
from app.middleware.metrics import MetricsMiddleware
from app.redis_client import close_redis, get_redis
from app.routers.carrier import router as carrier_router
from app.routers.chain import router as chain_router
from app.routers.dashboard import router as dashboard_router
from app.routers.health import router as health_router
from app.routers.loads import router as loads_router
from app.routers.markets import router as markets_router
from app.routers.recommend import router as recommend_router
from app.routers.simulate import router as simulate_router
from app.temporal.worker import start_temporal_worker, stop_temporal_worker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await get_pool()
    await get_redis()
    temporal_ok = await start_temporal_worker()
    app.state.temporal_available = temporal_ok
    if temporal_ok:
        logger.info("Temporal worker running")
    else:
        logger.warning("Temporal unavailable — chain optimization uses in-process fallback")
    yield
    await stop_temporal_worker()
    await close_redis()
    await close_pool()


app = FastAPI(
    title="DeadMile AI Gateway",
    description="Single entry point for load optimization, markets, and agent recommendations",
    version="1.0.0",
    lifespan=lifespan,
)

setup_cors(app)
app.add_middleware(ApiKeyMiddleware)
app.add_middleware(MetricsMiddleware)

app.include_router(health_router)
app.include_router(loads_router)
app.include_router(recommend_router)
app.include_router(markets_router)
app.include_router(simulate_router)
app.include_router(chain_router)
app.include_router(dashboard_router)
app.include_router(carrier_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": settings.service_name}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type="text/plain; version=0.0.4; charset=utf-8")


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "DeadMile AI API Gateway",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "health_all": "/health/all",
    }
