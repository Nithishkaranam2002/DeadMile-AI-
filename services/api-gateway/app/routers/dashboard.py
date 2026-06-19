"""Aggregated dashboard stats with Redis cache."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings
from app.db import get_pool
from app.proxy import proxy_json
from app.redis_client import get_redis

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

CACHE_KEY = "dashboard:stats"
CACHE_TTL = 300


@router.get("/stats")
async def dashboard_stats() -> dict:
    redis = await get_redis()
    cached = await redis.get(CACHE_KEY)
    if cached:
        return json.loads(cached)

    pool = await get_pool()
    async with pool.acquire() as conn:
        totals = await conn.fetchrow(
            """
            SELECT COUNT(*) AS total_loads,
                   AVG(rate_per_mile) AS avg_rate_per_mile,
                   AVG(miles) AS avg_miles,
                   MIN(pickup_start) AS earliest_pickup,
                   MAX(delivery_end) AS latest_delivery
            FROM loads
            """
        )
        equipment_rows = await conn.fetch(
            "SELECT equipment, COUNT(*) AS cnt FROM loads GROUP BY equipment ORDER BY cnt DESC"
        )
        commodity_row = await conn.fetchrow(
            "SELECT commodity, COUNT(*) AS cnt FROM loads GROUP BY commodity ORDER BY cnt DESC LIMIT 1"
        )
        market_count = await conn.fetchval("SELECT COUNT(*) FROM market_scores")

    equipment_distribution = {r["equipment"]: r["cnt"] for r in equipment_rows}

    best_market = {"city": "Atlanta", "state": "GA", "score": 0}
    try:
        markets = await proxy_json(
            "GET",
            f"{settings.market_intelligence_url}/markets/top",
            params={"limit": 1},
        )
        if markets:
            m = markets[0]
            best_market = {
                "city": m.get("city", ""),
                "state": m.get("state", ""),
                "score": m.get("market_score", 0),
            }
    except Exception:
        pass

    avg_net_profit = 0.0
    try:
        what_if = await proxy_json(
            "POST",
            f"{settings.profitability_engine_url}/calculate/what-if",
            json_body={"lat": 39.8, "lng": -98.5, "equipment": "Dry Van"},
            timeout=60.0,
        )
        avg_net_profit = what_if.get("avg_net_profit", 0.0)
    except Exception:
        pass

    result = {
        "total_loads": int(totals["total_loads"] or 0),
        "avg_net_profit": round(float(avg_net_profit), 2),
        "best_market": f"{best_market['city']}, {best_market['state']}",
        "best_market_score": best_market["score"],
        "avg_rate_per_mile": round(float(totals["avg_rate_per_mile"] or 0), 2),
        "total_markets_scored": int(market_count or 0),
        "equipment_distribution": equipment_distribution,
        "top_commodity": commodity_row["commodity"] if commodity_row else "General freight",
        "avg_miles": round(float(totals["avg_miles"] or 0), 1),
        "date_range": {
            "earliest_pickup": totals["earliest_pickup"].isoformat() if totals["earliest_pickup"] else None,
            "latest_delivery": totals["latest_delivery"].isoformat() if totals["latest_delivery"] else None,
        },
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }

    await redis.setex(CACHE_KEY, CACHE_TTL, json.dumps(result, default=str))
    return result
