"""DeadMile AI — Load Processor Service"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import structlog
from fastapi import FastAPI
from prometheus_client import make_asgi_app

from app.db import close_pool, compute_market_scores, get_stats
from app.kafka_consumer import get_consumer
from app.rate_history import populate_rate_history
from shared.config import settings

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    consumer = get_consumer()
    consumer.set_event_loop(asyncio.get_running_loop())
    consumer.start()
    logger.info("load_processor_started", kafka_topic=settings.kafka_topic_loads)
    yield
    consumer.stop()
    await close_pool()


app = FastAPI(
    title="DeadMile AI — Load Processor",
    description="Kafka consumer that enriches loads with geocoding and stores in Postgres",
    version="0.2.0",
    lifespan=lifespan,
)

app.mount("/metrics", make_asgi_app())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "load-processor"}


@app.get("/stats")
async def stats() -> dict[str, Any]:
    db_stats = await get_stats()
    consumer_stats = get_consumer().get_status()
    return {**db_stats, "consumer": consumer_stats}


@app.post("/recompute-markets")
async def recompute_markets() -> dict[str, Any]:
    get_consumer().flush()
    markets = await compute_market_scores()
    lanes = await populate_rate_history()
    return {
        "market_scores_updated": markets,
        "rate_history_lanes": lanes,
    }


@app.post("/flush")
async def flush_consumer() -> dict[str, Any]:
    return await get_consumer().finalize_pipeline()
