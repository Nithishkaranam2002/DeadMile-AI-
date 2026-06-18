"""DeadMile AI — Market Intelligence Service"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional

import structlog
from fastapi import FastAPI, HTTPException
from prometheus_client import make_asgi_app
from pydantic import BaseModel, Field

from app.db import close_pool, get_pool
from app.market_clusterer import MarketClusterer
from app.market_scorer import MarketScorer
from app.rate_predictor import RatePredictor
from shared.cache import CacheManager
from shared.config import settings
from shared.models import MarketCluster, MarketScore, RatePrediction

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger(__name__)

scorer = MarketScorer()
predictor = RatePredictor()
clusterer = MarketClusterer()
cache = CacheManager(settings.redis_url)

MARKET_CACHE_TTL = 3600
RATE_CACHE_TTL = 21600


class PredictRequest(BaseModel):
    origin_city: str
    origin_state: str
    dest_city: str
    dest_state: str
    equipment: str = "Dry Van"
    days_ahead: int = Field(default=7, ge=1, le=90)
    miles: int = Field(default=500, ge=1)
    weight_lbs: int = Field(default=35000, ge=1)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await cache.connect()
    pool = await get_pool()
    try:
        await scorer.compute_all_market_scores(pool)
    except Exception as exc:
        logger.warning("startup_market_scoring_skipped", error=str(exc))
    logger.info("market_intelligence_started")
    yield
    await cache.close()
    await close_pool()


app = FastAPI(
    title="DeadMile AI — Market Intelligence",
    description="Market scoring, XGBoost rate prediction, K-Means clustering",
    version="0.3.0",
    lifespan=lifespan,
)

app.mount("/metrics", make_asgi_app())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "market-intelligence"}


@app.get("/markets/heatmap")
async def market_heatmap() -> list[dict[str, Any]]:
    cached = await cache.get("markets:heatmap")
    if cached and isinstance(cached.get("data"), list):
        return cached["data"]

    pool = await get_pool()
    data = await scorer.get_market_heatmap_data(pool)
    await cache.set("markets:heatmap", {"data": data}, ttl=MARKET_CACHE_TTL)
    return data


@app.get("/markets/clusters", response_model=list[MarketCluster])
async def market_clusters() -> list[MarketCluster]:
    pool = await get_pool()
    return await clusterer.cluster_markets(pool)


@app.get("/markets/top", response_model=list[MarketScore])
async def top_markets(limit: int = 10) -> list[MarketScore]:
    cache_key = f"markets:top:{limit}"
    cached = await cache.get(cache_key)
    if cached and isinstance(cached.get("data"), list):
        return [MarketScore.model_validate(m) for m in cached["data"]]

    pool = await get_pool()
    markets = await scorer.get_top_markets(limit, pool)
    await cache.set(cache_key, {"data": [m.model_dump() for m in markets]}, ttl=MARKET_CACHE_TTL)
    return markets


@app.get("/markets/{city}/{state}", response_model=MarketScore)
async def market_detail(city: str, state: str) -> MarketScore:
    cache_key = f"market:{city.lower()}:{state.upper()}"
    cached = await cache.get(cache_key)
    if cached:
        return MarketScore.model_validate(cached)

    pool = await get_pool()
    market = await scorer.get_market_score(city, state, pool)
    if not market:
        raise HTTPException(status_code=404, detail=f"Market not found: {city}, {state}")
    await cache.set(cache_key, market.model_dump(), ttl=MARKET_CACHE_TTL)
    return market


@app.post("/rates/predict", response_model=RatePrediction)
async def predict_rate(req: PredictRequest) -> RatePrediction:
    cache_key = (
        f"rate:{req.origin_city}:{req.origin_state}:{req.dest_city}:"
        f"{req.dest_state}:{req.equipment}:{req.days_ahead}"
    )
    cached = await cache.get(cache_key)
    if cached:
        return RatePrediction.model_validate(cached)

    pool = await get_pool()
    prediction = await predictor.predict(
        pool,
        req.origin_city,
        req.origin_state,
        req.dest_city,
        req.dest_state,
        req.equipment,
        req.days_ahead,
        req.miles,
        req.weight_lbs,
    )
    await cache.set(cache_key, prediction.model_dump(), ttl=RATE_CACHE_TTL)
    return prediction


@app.post("/rates/train")
async def train_rate_model() -> dict[str, Any]:
    pool = await get_pool()
    result = await predictor.train_from_db(pool)
    await cache.invalidate("rate:*")
    return {"status": "trained", **result}


@app.get("/rates/history/{origin_state}/{dest_state}")
async def rate_history(origin_state: str, dest_state: str, equipment: Optional[str] = None) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if equipment:
            rows = await conn.fetch(
                """
                SELECT time, origin_city, origin_state, dest_city, dest_state,
                       equipment, avg_rate_per_mile, load_count
                FROM rate_history
                WHERE origin_state = $1 AND dest_state = $2 AND equipment = $3
                ORDER BY time DESC LIMIT 100
                """,
                origin_state.upper(),
                dest_state.upper(),
                equipment,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT time, origin_city, origin_state, dest_city, dest_state,
                       equipment, avg_rate_per_mile, load_count
                FROM rate_history
                WHERE origin_state = $1 AND dest_state = $2
                ORDER BY time DESC LIMIT 100
                """,
                origin_state.upper(),
                dest_state.upper(),
            )
    return [
        {
            "time": r["time"].isoformat() if r["time"] else None,
            "origin": f"{r['origin_city']}, {r['origin_state']}",
            "destination": f"{r['dest_city']}, {r['dest_state']}",
            "equipment": r["equipment"],
            "avg_rate_per_mile": float(r["avg_rate_per_mile"] or 0),
            "load_count": r["load_count"],
        }
        for r in rows
    ]


@app.post("/markets/recompute")
async def recompute_markets() -> dict[str, Any]:
    pool = await get_pool()
    scores = await scorer.compute_all_market_scores(pool)
    await cache.invalidate("market:*")
    await cache.invalidate("markets:*")
    return {"status": "ok", "markets_updated": len(scores)}
