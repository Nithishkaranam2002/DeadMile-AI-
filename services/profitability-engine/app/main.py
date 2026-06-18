"""DeadMile AI — Profitability Engine"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional

import structlog
from fastapi import FastAPI, HTTPException
from prometheus_client import make_asgi_app
from pydantic import BaseModel, Field

from app.batch import BatchCalculator
from app.calculator import ProfitabilityCalculator
from app.db import close_pool, get_load_by_id, get_market_score, get_pool
from app.deadhead import estimate_post_delivery_deadhead
from shared.cache import CacheManager
from shared.config import settings
from shared.cost_settings import cost_settings
from shared.models import ProfitBreakdown

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger(__name__)

calculator = ProfitabilityCalculator()
batch_calculator = BatchCalculator(calculator)
cache = CacheManager(settings.redis_url)

PROFIT_CACHE_TTL = 900  # 15 minutes


class CalculateRequest(BaseModel):
    load_id: str
    driver_lat: float
    driver_lng: float
    fuel_price_override: Optional[float] = None


class BatchRequest(BaseModel):
    driver_lat: float
    driver_lng: float
    equipment: str = "Dry Van"
    max_deadhead_miles: int = Field(default=250, ge=0, le=500)
    limit: int = Field(default=20, ge=1, le=100)
    fuel_price_override: Optional[float] = None


class WhatIfRequest(BaseModel):
    lat: float
    lng: float
    equipment: Optional[str] = None
    fuel_price_override: Optional[float] = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await cache.connect()
    logger.info("profitability_engine_started")
    yield
    await cache.close()
    await close_pool()


app = FastAPI(
    title="DeadMile AI — Profitability Engine",
    description="Calculates true net profit: revenue - all cost components",
    version="0.3.0",
    lifespan=lifespan,
)

app.mount("/metrics", make_asgi_app())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "profitability-engine"}


@app.get("/constants")
async def cost_constants() -> dict[str, Any]:
    return {
        "fuel_price_per_gallon": cost_settings.fuel_price_per_gallon,
        "avg_mpg_loaded": cost_settings.avg_mpg_loaded,
        "avg_mpg_empty": cost_settings.avg_mpg_empty,
        "driver_cpm": cost_settings.driver_cpm,
        "insurance_per_mile": cost_settings.insurance_per_mile,
        "maintenance_per_mile": cost_settings.maintenance_per_mile,
        "tolls_per_mile": cost_settings.tolls_per_mile,
        "dispatch_fee_percent": cost_settings.dispatch_fee_percent,
        "factoring_fee_percent": cost_settings.factoring_fee_percent,
        "overhead_per_mile": cost_settings.overhead_per_mile,
        "team_driver_multiplier": cost_settings.team_driver_multiplier,
        "hazmat_premium": cost_settings.hazmat_premium,
    }


@app.post("/calculate", response_model=ProfitBreakdown)
async def calculate_single(req: CalculateRequest) -> ProfitBreakdown:
    cache_key = f"profit:{req.load_id}:{req.driver_lat:.2f}:{req.driver_lng:.2f}"
    cached = await cache.get(cache_key)
    if cached:
        return ProfitBreakdown.model_validate(cached)

    load = await get_load_by_id(req.load_id)
    if not load:
        raise HTTPException(status_code=404, detail=f"Load {req.load_id} not found")

    dest_score = await get_market_score(load.dest_city, load.dest_state)
    pool = await get_pool()
    deadhead_from = await estimate_post_delivery_deadhead(
        load.dest_city, load.dest_state, load.equipment, pool
    )

    breakdown = calculator.calculate(
        load,
        req.driver_lat,
        req.driver_lng,
        fuel_price_override=req.fuel_price_override,
        destination_market_score=dest_score,
        deadhead_from_delivery=deadhead_from,
    )
    await cache.set(cache_key, breakdown.model_dump(mode="json"), ttl=PROFIT_CACHE_TTL)
    return breakdown


@app.post("/calculate/batch", response_model=list[ProfitBreakdown])
async def calculate_batch(req: BatchRequest) -> list[ProfitBreakdown]:
    return await batch_calculator.calculate_top_loads(
        req.driver_lat,
        req.driver_lng,
        req.equipment,
        req.max_deadhead_miles,
        req.limit,
        req.fuel_price_override,
    )


@app.post("/calculate/what-if")
async def calculate_what_if(req: WhatIfRequest) -> dict[str, Any]:
    return await batch_calculator.calculate_all_from_location(
        req.lat, req.lng, req.equipment, req.fuel_price_override
    )
