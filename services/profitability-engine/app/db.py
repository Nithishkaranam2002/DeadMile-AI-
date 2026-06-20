"""Database access for profitability engine."""

from __future__ import annotations

from typing import Any, Optional

import asyncpg

from shared.config import settings
from shared.models import LoadRecord

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=settings.asyncpg_dsn,
            min_size=5,
            max_size=20,
            command_timeout=60,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _row_to_load(row: asyncpg.Record) -> LoadRecord:
    return LoadRecord(
        load_id=row["load_id"],
        origin_city=row["origin_city"],
        origin_state=row["origin_state"],
        origin_zip=row["origin_zip"],
        origin_lat=float(row["origin_lat"]) if row["origin_lat"] is not None else None,
        origin_lng=float(row["origin_lng"]) if row["origin_lng"] is not None else None,
        dest_city=row["dest_city"],
        dest_state=row["dest_state"],
        dest_zip=row["dest_zip"],
        dest_lat=float(row["dest_lat"]) if row["dest_lat"] is not None else None,
        dest_lng=float(row["dest_lng"]) if row["dest_lng"] is not None else None,
        pickup_start=row["pickup_start"],
        pickup_end=row["pickup_end"],
        delivery_start=row["delivery_start"],
        delivery_end=row["delivery_end"],
        equipment=row["equipment"],
        commodity=row["commodity"],
        weight_lbs=row["weight_lbs"],
        miles=row["miles"],
        rate=float(row["rate"]),
        rate_per_mile=float(row["rate_per_mile"]),
        requirements=row["requirements"],
        source=row["source"],
    )


_LOAD_SELECT = """
    SELECT load_id, origin_city, origin_state, origin_zip,
           ST_Y(origin_point::geometry) AS origin_lat,
           ST_X(origin_point::geometry) AS origin_lng,
           dest_city, dest_state, dest_zip,
           ST_Y(dest_point::geometry) AS dest_lat,
           ST_X(dest_point::geometry) AS dest_lng,
           pickup_start, pickup_end, delivery_start, delivery_end,
           equipment, commodity, weight_lbs, miles, rate, rate_per_mile,
           requirements, source
    FROM loads
"""


async def get_load_by_id(load_id: str) -> Optional[LoadRecord]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(f"{_LOAD_SELECT} WHERE load_id = $1", load_id)
    return _row_to_load(row) if row else None


async def get_loads_near_driver(
    driver_lat: float,
    driver_lng: float,
    equipment: str,
    max_deadhead_miles: int,
    limit: int = 100,
) -> list[LoadRecord]:
    """PostGIS query for loads within deadhead range of driver."""
    pool = await get_pool()
    meters = max_deadhead_miles * 1609.344
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            {_LOAD_SELECT}
            WHERE equipment = $1
              AND origin_point IS NOT NULL
              AND ST_DWithin(
                    origin_point,
                    ST_SetSRID(ST_MakePoint($2, $3), 4326)::geography,
                    $4
                  )
            ORDER BY rate DESC
            LIMIT $5
            """,
            equipment,
            driver_lng,
            driver_lat,
            meters,
            limit,
        )
    return [_row_to_load(r) for r in rows]


async def get_loads_by_equipment(equipment: Optional[str] = None, limit: int = 500) -> list[LoadRecord]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if equipment:
            rows = await conn.fetch(f"{_LOAD_SELECT} WHERE equipment = $1 LIMIT $2", equipment, limit)
        else:
            rows = await conn.fetch(f"{_LOAD_SELECT} LIMIT $1", limit)
    return [_row_to_load(r) for r in rows]


async def get_market_score(city: str, state: str) -> Optional[float]:
    city = city.strip()
    state = state.strip().upper()
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT market_score FROM market_scores
            WHERE LOWER(TRIM(city)) = LOWER($1) AND UPPER(TRIM(state)) = $2
            """,
            city,
            state,
        )
    return float(row["market_score"]) if row and row["market_score"] is not None else None
