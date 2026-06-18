"""Async PostgreSQL database operations for load storage."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import asyncpg
import structlog

from shared.config import settings
from shared.geocoding import geocode_city
from shared.models import LoadRecord

logger = structlog.get_logger(__name__)

_pool: asyncpg.Pool | None = None


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


def enrich_coordinates(load: LoadRecord) -> LoadRecord:
    """Fill missing lat/lng from static geocoding lookup."""
    updates: dict[str, float] = {}
    if load.origin_lat is None or load.origin_lng is None:
        lat, lng = geocode_city(load.origin_city, load.origin_state)
        updates["origin_lat"] = lat
        updates["origin_lng"] = lng
    if load.dest_lat is None or load.dest_lng is None:
        lat, lng = geocode_city(load.dest_city, load.dest_state)
        updates["dest_lat"] = lat
        updates["dest_lng"] = lng
    if updates:
        return load.model_copy(update=updates)
    return load


UPSERT_SQL = """
INSERT INTO loads (
    load_id, origin_city, origin_state, origin_zip, origin_point,
    dest_city, dest_state, dest_zip, dest_point,
    pickup_start, pickup_end, delivery_start, delivery_end,
    equipment, commodity, weight_lbs, miles, rate, rate_per_mile,
    requirements, source
) VALUES (
    $1, $2, $3, $4,
    ST_SetSRID(ST_MakePoint($5, $6), 4326)::geography,
    $7, $8, $9,
    ST_SetSRID(ST_MakePoint($10, $11), 4326)::geography,
    $12, $13, $14, $15,
    $16, $17, $18, $19, $20, $21, $22, $23
)
ON CONFLICT (load_id) DO UPDATE SET
    origin_city = EXCLUDED.origin_city,
    origin_state = EXCLUDED.origin_state,
    origin_zip = EXCLUDED.origin_zip,
    origin_point = EXCLUDED.origin_point,
    dest_city = EXCLUDED.dest_city,
    dest_state = EXCLUDED.dest_state,
    dest_zip = EXCLUDED.dest_zip,
    dest_point = EXCLUDED.dest_point,
    pickup_start = EXCLUDED.pickup_start,
    pickup_end = EXCLUDED.pickup_end,
    delivery_start = EXCLUDED.delivery_start,
    delivery_end = EXCLUDED.delivery_end,
    equipment = EXCLUDED.equipment,
    commodity = EXCLUDED.commodity,
    weight_lbs = EXCLUDED.weight_lbs,
    miles = EXCLUDED.miles,
    rate = EXCLUDED.rate,
    rate_per_mile = EXCLUDED.rate_per_mile,
    requirements = EXCLUDED.requirements,
    source = EXCLUDED.source
"""


def _load_to_args(load: LoadRecord) -> tuple[Any, ...]:
    enriched = enrich_coordinates(load)
    assert enriched.origin_lat is not None and enriched.origin_lng is not None
    assert enriched.dest_lat is not None and enriched.dest_lng is not None
    return (
        enriched.load_id,
        enriched.origin_city,
        enriched.origin_state,
        enriched.origin_zip,
        enriched.origin_lng,
        enriched.origin_lat,
        enriched.dest_city,
        enriched.dest_state,
        enriched.dest_zip,
        enriched.dest_lng,
        enriched.dest_lat,
        enriched.pickup_start,
        enriched.pickup_end,
        enriched.delivery_start,
        enriched.delivery_end,
        enriched.equipment,
        enriched.commodity,
        enriched.weight_lbs,
        enriched.miles,
        enriched.rate,
        enriched.rate_per_mile,
        enriched.requirements,
        enriched.source,
    )


async def insert_load(load: LoadRecord) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(UPSERT_SQL, *_load_to_args(load))


async def insert_loads_batch(loads: list[LoadRecord]) -> int:
    if not loads:
        return 0
    pool = await get_pool()
    args_list = [_load_to_args(load) for load in loads]
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.executemany(UPSERT_SQL, args_list)
    return len(loads)


async def get_load_count() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM loads")


async def get_stats() -> dict[str, Any]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM loads")
        by_equipment = await conn.fetch(
            "SELECT equipment, COUNT(*) AS cnt FROM loads GROUP BY equipment ORDER BY cnt DESC"
        )
        by_state = await conn.fetch(
            "SELECT origin_state, COUNT(*) AS cnt FROM loads GROUP BY origin_state ORDER BY cnt DESC LIMIT 20"
        )
    return {
        "total_loads": total,
        "by_equipment": {r["equipment"]: r["cnt"] for r in by_equipment},
        "by_origin_state": {r["origin_state"]: r["cnt"] for r in by_state},
    }


async def compute_market_scores() -> int:
    """Aggregate market scores per city and upsert into market_scores table."""
    pool = await get_pool()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH outbound AS (
                SELECT origin_city AS city, origin_state AS state,
                       AVG(ST_Y(origin_point::geometry)) AS lat,
                       AVG(ST_X(origin_point::geometry)) AS lng,
                       COUNT(*) AS outbound_count,
                       AVG(rate_per_mile) AS avg_outbound_rate
                FROM loads
                WHERE origin_point IS NOT NULL
                GROUP BY origin_city, origin_state
            ),
            inbound AS (
                SELECT dest_city AS city, dest_state AS state,
                       COUNT(*) AS inbound_count,
                       AVG(rate_per_mile) AS avg_inbound_rate
                FROM loads
                GROUP BY dest_city, dest_state
            ),
            combined AS (
                SELECT
                    COALESCE(o.city, i.city) AS city,
                    COALESCE(o.state, i.state) AS state,
                    o.lat, o.lng,
                    COALESCE(o.outbound_count, 0) AS outbound_load_count,
                    COALESCE(o.avg_outbound_rate, 0) AS avg_outbound_rate,
                    COALESCE(i.avg_inbound_rate, 0) AS avg_inbound_rate,
                    COALESCE(i.inbound_count, 0) AS inbound_count
                FROM outbound o
                FULL OUTER JOIN inbound i
                    ON o.city = i.city AND o.state = i.state
            )
            SELECT city, state, lat, lng, outbound_load_count,
                   avg_outbound_rate, avg_inbound_rate, inbound_count
            FROM combined
            WHERE city IS NOT NULL
            """
        )

        upserted = 0
        for row in rows:
            outbound = row["outbound_load_count"] or 0
            inbound = row["inbound_count"] or 0
            avg_out = float(row["avg_outbound_rate"] or 0)
            lane_balance = outbound / inbound if inbound > 0 else float(outbound)
            avg_deadhead_estimate = 150.0
            market_score = (outbound * avg_out) / (1 + avg_deadhead_estimate)

            lat = row["lat"]
            lng = row["lng"]
            if lat is None or lng is None:
                lat, lng = geocode_city(row["city"], row["state"])

            await conn.execute(
                """
                INSERT INTO market_scores (
                    city, state, point, outbound_load_count,
                    avg_outbound_rate, avg_inbound_rate,
                    lane_balance_ratio, market_score, updated_at
                ) VALUES (
                    $1, $2,
                    ST_SetSRID(ST_MakePoint($3, $4), 4326)::geography,
                    $5, $6, $7, $8, $9, $10
                )
                ON CONFLICT (city, state) DO UPDATE SET
                    point = EXCLUDED.point,
                    outbound_load_count = EXCLUDED.outbound_load_count,
                    avg_outbound_rate = EXCLUDED.avg_outbound_rate,
                    avg_inbound_rate = EXCLUDED.avg_inbound_rate,
                    lane_balance_ratio = EXCLUDED.lane_balance_ratio,
                    market_score = EXCLUDED.market_score,
                    updated_at = EXCLUDED.updated_at
                """,
                row["city"],
                row["state"],
                lng,
                lat,
                outbound,
                avg_out,
                float(row["avg_inbound_rate"] or 0),
                lane_balance,
                market_score,
                now,
            )
            upserted += 1

    logger.info("market_scores_computed", cities=upserted)
    return upserted
