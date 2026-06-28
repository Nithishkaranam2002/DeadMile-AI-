"""Upsert loads into Postgres — shared by live feed and processor."""

from __future__ import annotations

from typing import Any

import asyncpg

from shared.geocoding import geocode_city
from shared.models import LoadRecord

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
    origin_point = EXCLUDED.origin_point,
    dest_city = EXCLUDED.dest_city,
    dest_state = EXCLUDED.dest_state,
    dest_point = EXCLUDED.dest_point,
    equipment = EXCLUDED.equipment,
    commodity = EXCLUDED.commodity,
    miles = EXCLUDED.miles,
    rate = EXCLUDED.rate,
    rate_per_mile = EXCLUDED.rate_per_mile,
    requirements = EXCLUDED.requirements,
    source = EXCLUDED.source
"""


def enrich_coordinates(load: LoadRecord) -> LoadRecord:
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


def normalize_live_load(raw: dict[str, Any], source: str = "live") -> LoadRecord | None:
    """Map broker / load board JSON to LoadRecord."""
    load_id = str(raw.get("load_id") or raw.get("id") or raw.get("reference") or "").strip()
    if not load_id:
        return None

    origin_city = str(raw.get("origin_city") or raw.get("originCity") or "").strip()
    origin_state = str(raw.get("origin_state") or raw.get("originState") or "")[:2].upper()
    dest_city = str(raw.get("dest_city") or raw.get("destination_city") or raw.get("destCity") or "").strip()
    dest_state = str(raw.get("dest_state") or raw.get("destination_state") or raw.get("destState") or "")[:2].upper()

    if not origin_city and raw.get("origin"):
        parts = str(raw["origin"]).split(",")
        origin_city = parts[0].strip()
        origin_state = parts[1].strip()[:2].upper() if len(parts) > 1 else "XX"
    if not dest_city and raw.get("destination"):
        parts = str(raw["destination"]).split(",")
        dest_city = parts[0].strip()
        dest_state = parts[1].strip()[:2].upper() if len(parts) > 1 else "XX"

    if not origin_city or not dest_city:
        return None

    try:
        miles = int(raw.get("miles") or raw.get("distance") or 0)
        rate = float(raw.get("rate") or raw.get("price") or raw.get("pay") or 0)
    except (TypeError, ValueError):
        return None
    if miles <= 0 or rate <= 0:
        return None

    equipment = str(raw.get("equipment") or raw.get("trailer_type") or "Dry Van")
    return LoadRecord(
        load_id=load_id[:64],
        origin_city=origin_city,
        origin_state=origin_state or "XX",
        dest_city=dest_city,
        dest_state=dest_state or "XX",
        equipment=equipment,
        commodity=str(raw.get("commodity") or "General freight"),
        weight_lbs=int(raw.get("weight_lbs") or raw.get("weight") or 40000),
        miles=miles,
        rate=rate,
        rate_per_mile=round(rate / miles, 2),
        requirements=raw.get("requirements"),
        source=source,
    )


async def upsert_loads(pool: asyncpg.Pool, loads: list[LoadRecord]) -> int:
    if not loads:
        return 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            for load in loads:
                await conn.execute(UPSERT_SQL, *_load_to_args(load))
    return len(loads)
