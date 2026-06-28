"""DeadMile AI — Profitability Engine"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional

import structlog
from fastapi import FastAPI, HTTPException
from prometheus_client import make_asgi_app
from pydantic import BaseModel, Field

from app.routing_service import deadhead_road_miles, loaded_lane_miles, set_routing_cache
from app.batch import BatchCalculator
from app.calculator import ProfitabilityCalculator
from shared.models import LoadRecord

from app.db import close_pool, get_load_by_id, get_market_score, get_pool
from app.deadhead import estimate_post_delivery_deadhead
from shared.cache import CacheManager
from shared.config import settings
from shared.cost_settings import cost_settings, merge_cost_settings
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


async def _routing_for_load(load, driver_lat: float, driver_lng: float) -> tuple[float, int]:
    pickup_lat = load.origin_lat or driver_lat
    pickup_lng = load.origin_lng or driver_lng
    dest_lat = load.dest_lat or pickup_lat
    dest_lng = load.dest_lng or pickup_lng
    deadhead_to, _ = await deadhead_road_miles(driver_lat, driver_lng, pickup_lat, pickup_lng)
    loaded_miles, _ = await loaded_lane_miles(pickup_lat, pickup_lng, dest_lat, dest_lng, load.miles)
    return deadhead_to, loaded_miles


class CostOverrides(BaseModel):
    fuel_price_per_gallon: Optional[float] = None
    avg_mpg_loaded: Optional[float] = None
    avg_mpg_empty: Optional[float] = None
    driver_cpm: Optional[float] = None
    insurance_per_mile: Optional[float] = None
    maintenance_per_mile: Optional[float] = None
    tolls_per_mile: Optional[float] = None
    dispatch_fee_percent: Optional[float] = None
    factoring_fee_percent: Optional[float] = None
    overhead_per_mile: Optional[float] = None


class CalculateRequest(BaseModel):
    load_id: str
    driver_lat: float
    driver_lng: float
    fuel_price_override: Optional[float] = None
    cost_overrides: Optional[CostOverrides] = None


class BatchRequest(BaseModel):
    driver_lat: float
    driver_lng: float
    equipment: str = "Dry Van"
    max_deadhead_miles: int = Field(default=250, ge=0, le=500)
    limit: int = Field(default=20, ge=1, le=100)
    fuel_price_override: Optional[float] = None
    cost_overrides: Optional[CostOverrides] = None


class WhatIfRequest(BaseModel):
    lat: float
    lng: float
    equipment: Optional[str] = None
    fuel_price_override: Optional[float] = None
    cost_overrides: Optional[CostOverrides] = None


class AdHocCalculateRequest(BaseModel):
    load_id: str = "IMPORT-1"
    origin_city: str
    origin_state: str
    origin_lat: Optional[float] = None
    origin_lng: Optional[float] = None
    dest_city: str
    dest_state: str
    dest_lat: Optional[float] = None
    dest_lng: Optional[float] = None
    miles: int = Field(..., ge=1)
    rate: float = Field(..., gt=0)
    equipment: str = "Dry Van"
    commodity: str = "General freight"
    weight_lbs: int = 40000
    driver_lat: float
    driver_lng: float
    fuel_price_override: Optional[float] = None
    cost_overrides: Optional[CostOverrides] = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await cache.connect()
    set_routing_cache(cache)
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

    dest_city = load.dest_city.strip()
    dest_state = load.dest_state.strip().upper()
    dest_score = await get_market_score(dest_city, dest_state)
    pool = await get_pool()
    deadhead_from = await estimate_post_delivery_deadhead(
        dest_city, dest_state, load.equipment, pool
    )

    overrides = req.cost_overrides.model_dump(exclude_none=True) if req.cost_overrides else None
    calc = ProfitabilityCalculator(settings=merge_cost_settings(overrides))
    deadhead_to, loaded_miles = await _routing_for_load(load, req.driver_lat, req.driver_lng)

    breakdown = calc.calculate(
        load,
        req.driver_lat,
        req.driver_lng,
        fuel_price_override=req.fuel_price_override,
        destination_market_score=dest_score,
        deadhead_from_delivery=deadhead_from,
        deadhead_to_miles=deadhead_to,
        loaded_miles_override=loaded_miles,
    )
    await cache.set(cache_key, breakdown.model_dump(mode="json"), ttl=PROFIT_CACHE_TTL)
    return breakdown


@app.post("/calculate/ad-hoc", response_model=ProfitBreakdown)
async def calculate_ad_hoc(req: AdHocCalculateRequest) -> ProfitBreakdown:
    """Calculate profitability for an inline load (import/compare) without DB lookup."""
    load = LoadRecord(
        load_id=req.load_id,
        origin_city=req.origin_city,
        origin_state=req.origin_state,
        origin_lat=req.origin_lat,
        origin_lng=req.origin_lng,
        dest_city=req.dest_city,
        dest_state=req.dest_state,
        dest_lat=req.dest_lat,
        dest_lng=req.dest_lng,
        equipment=req.equipment,
        commodity=req.commodity,
        weight_lbs=req.weight_lbs,
        miles=req.miles,
        rate=req.rate,
        rate_per_mile=round(req.rate / req.miles, 2) if req.miles else 0.0,
        source="import",
    )

    dest_city = load.dest_city.strip()
    dest_state = load.dest_state.strip().upper()
    dest_score = await get_market_score(dest_city, dest_state)
    pool = await get_pool()
    deadhead_from = await estimate_post_delivery_deadhead(
        dest_city, dest_state, load.equipment, pool
    )

    overrides = req.cost_overrides.model_dump(exclude_none=True) if req.cost_overrides else None
    calc = ProfitabilityCalculator(settings=merge_cost_settings(overrides))
    deadhead_to, loaded_miles = await _routing_for_load(load, req.driver_lat, req.driver_lng)

    return calc.calculate(
        load,
        req.driver_lat,
        req.driver_lng,
        fuel_price_override=req.fuel_price_override,
        destination_market_score=dest_score,
        deadhead_from_delivery=deadhead_from,
        deadhead_to_miles=deadhead_to,
        loaded_miles_override=loaded_miles,
    )


@app.post("/calculate/batch", response_model=list[ProfitBreakdown])
async def calculate_batch(req: BatchRequest) -> list[ProfitBreakdown]:
    overrides = req.cost_overrides.model_dump(exclude_none=True) if req.cost_overrides else None
    calc = BatchCalculator(ProfitabilityCalculator(settings=merge_cost_settings(overrides)))
    return await calc.calculate_top_loads(
        req.driver_lat,
        req.driver_lng,
        req.equipment,
        req.max_deadhead_miles,
        req.limit,
        req.fuel_price_override,
    )


@app.post("/calculate/what-if")
async def calculate_what_if(req: WhatIfRequest) -> dict[str, Any]:
    overrides = req.cost_overrides.model_dump(exclude_none=True) if req.cost_overrides else None
    calc = BatchCalculator(ProfitabilityCalculator(settings=merge_cost_settings(overrides)))
    return await calc.calculate_all_from_location(
        req.lat, req.lng, req.equipment, req.fuel_price_override
    )
