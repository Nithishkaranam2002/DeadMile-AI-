"""Load search endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.db import get_pool

router = APIRouter(prefix="/loads", tags=["loads"])


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
    meters = radius * 1609.344

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

    query = f"""
        SELECT load_id, origin_city, origin_state, dest_city, dest_state,
               equipment, commodity, miles, rate, rate_per_mile, requirements,
               ST_Y(origin_point::geometry) AS origin_lat,
               ST_X(origin_point::geometry) AS origin_lng,
               ST_Y(dest_point::geometry) AS dest_lat,
               ST_X(dest_point::geometry) AS dest_lng
        FROM loads
        WHERE {where}
        ORDER BY rate DESC
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
        }
        for r in rows
    ]
    return {"loads": loads, "count": len(loads)}


@router.get("/{load_id}")
async def get_load(load_id: str) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT load_id, origin_city, origin_state, dest_city, dest_state,
                   equipment, commodity, miles, rate, rate_per_mile, requirements
            FROM loads WHERE load_id = $1
            """,
            load_id,
        )
    if not row:
        return {"error": "not found"}
    return dict(row)
