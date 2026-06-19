"""Load search and stats endpoints."""

from __future__ import annotations

import math
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.db import get_pool

router = APIRouter(prefix="/loads", tags=["loads"])


def _haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a)) * 1.3


@router.get("/search")
async def search_loads(
    lat: float = Query(..., description="Driver latitude"),
    lng: float = Query(..., description="Driver longitude"),
    radius: int = Query(250, ge=1, le=500, description="Search radius in miles"),
    equipment: Optional[str] = Query(None),
    min_rate: Optional[float] = Query(None),
    max_miles: Optional[int] = Query(None),
    commodity: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    pool = await get_pool()
    meters = radius * 1609.34

    conditions = [
        "origin_point IS NOT NULL",
        "ST_DWithin(origin_point, ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography, $3)",
    ]
    params: list = [lng, lat, meters]
    idx = 4

    if equipment:
        conditions.append(f"equipment = ${idx}")
        params.append(equipment)
        idx += 1
    if min_rate is not None:
        conditions.append(f"rate >= ${idx}")
        params.append(min_rate)
        idx += 1
    if max_miles is not None:
        conditions.append(f"miles <= ${idx}")
        params.append(max_miles)
        idx += 1
    if commodity:
        conditions.append(f"commodity ILIKE ${idx}")
        params.append(f"%{commodity}%")
        idx += 1

    params.append(limit)
    where = " AND ".join(conditions)
    origin_point = "ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography"

    query = f"""
        SELECT load_id, origin_city, origin_state, dest_city, dest_state,
               equipment, commodity, miles, rate, rate_per_mile, requirements,
               ST_Y(origin_point::geometry) AS origin_lat,
               ST_X(origin_point::geometry) AS origin_lng,
               ST_Y(dest_point::geometry) AS dest_lat,
               ST_X(dest_point::geometry) AS dest_lng,
               ST_Distance(origin_point, {origin_point}) / 1609.34 AS deadhead_miles
        FROM loads
        WHERE {where}
        ORDER BY ST_Distance(origin_point, {origin_point})
        LIMIT ${idx}
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    loads = [
        {
            "load_id": r["load_id"],
            "origin": f"{r['origin_city']}, {r['origin_state']}",
            "destination": f"{r['dest_city']}, {r['dest_state']}",
            "equipment": r["equipment"],
            "commodity": r["commodity"],
            "miles": r["miles"],
            "rate": float(r["rate"]),
            "rate_per_mile": float(r["rate_per_mile"]),
            "requirements": r["requirements"],
            "origin_lat": float(r["origin_lat"]) if r["origin_lat"] else None,
            "origin_lng": float(r["origin_lng"]) if r["origin_lng"] else None,
            "dest_lat": float(r["dest_lat"]) if r["dest_lat"] else None,
            "dest_lng": float(r["dest_lng"]) if r["dest_lng"] else None,
            "deadhead_miles": round(float(r["deadhead_miles"]), 1) if r["deadhead_miles"] else round(
                _haversine_miles(lat, lng, float(r["origin_lat"]), float(r["origin_lng"])), 1
            ) if r["origin_lat"] and r["origin_lng"] else None,
        }
        for r in rows
    ]
    return {"loads": loads, "count": len(loads)}


@router.get("/stats")
async def load_stats() -> dict:
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
        state_rows = await conn.fetch(
            "SELECT origin_state AS state, COUNT(*) AS cnt FROM loads GROUP BY origin_state ORDER BY cnt DESC LIMIT 20"
        )

    return {
        "total_loads": int(totals["total_loads"] or 0),
        "loads_by_equipment": {r["equipment"]: r["cnt"] for r in equipment_rows},
        "loads_by_state": {r["state"]: r["cnt"] for r in state_rows},
        "avg_rate_per_mile": round(float(totals["avg_rate_per_mile"] or 0), 2),
        "avg_miles": round(float(totals["avg_miles"] or 0), 1),
        "date_range": {
            "earliest_pickup": totals["earliest_pickup"].isoformat() if totals["earliest_pickup"] else None,
            "latest_delivery": totals["latest_delivery"].isoformat() if totals["latest_delivery"] else None,
        },
    }


@router.get("/{load_id}")
async def get_load(load_id: str) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT load_id, origin_city, origin_state, dest_city, dest_state,
                   equipment, commodity, miles, rate, rate_per_mile, requirements,
                   ST_Y(origin_point::geometry) AS origin_lat,
                   ST_X(origin_point::geometry) AS origin_lng,
                   ST_Y(dest_point::geometry) AS dest_lat,
                   ST_X(dest_point::geometry) AS dest_lng
            FROM loads WHERE load_id = $1
            """,
            load_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail=f"Load {load_id} not found")
    return {
        "load_id": row["load_id"],
        "origin": f"{row['origin_city']}, {row['origin_state']}",
        "destination": f"{row['dest_city']}, {row['dest_state']}",
        "equipment": row["equipment"],
        "commodity": row["commodity"],
        "miles": row["miles"],
        "rate": float(row["rate"]),
        "rate_per_mile": float(row["rate_per_mile"]),
        "requirements": row["requirements"],
        "origin_lat": float(row["origin_lat"]) if row["origin_lat"] else None,
        "origin_lng": float(row["origin_lng"]) if row["origin_lng"] else None,
        "dest_lat": float(row["dest_lat"]) if row["dest_lat"] else None,
        "dest_lng": float(row["dest_lng"]) if row["dest_lng"] else None,
    }
