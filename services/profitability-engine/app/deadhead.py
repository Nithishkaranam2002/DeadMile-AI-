"""Deadhead distance calculations."""

from __future__ import annotations

import math
from typing import Optional

import asyncpg

from shared import constants as c
from shared.cost_settings import cost_settings
from shared.geocoding import geocode_city


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great circle distance in miles."""
    r = 3958.8
    lat1_r, lng1_r, lat2_r, lng2_r = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat = lat2_r - lat1_r
    dlng = lng2_r - lng1_r
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


def road_distance_estimate(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance adjusted for road routing."""
    return haversine_distance(lat1, lng1, lat2, lng2) * cost_settings.road_factor


def estimate_deadhead_from_market_score(market_score: float, equipment: str) -> float:
    """
    Estimate post-delivery deadhead miles from normalized market score.
    Hot market (score ~100) → ~20 mi; dead market (score ~0) → ~150 mi.
    """
    normalized = max(0.0, min(100.0, market_score)) / 100.0
    base = 150.0 - (normalized * 130.0)
    miles = max(20.0, min(150.0, base))
    if equipment in ("Flatbed", "Step Deck"):
        miles *= c.FLATBED_DEADHEAD_MODIFIER
    return round(miles, 1)


async def estimate_post_delivery_deadhead(
    dest_city: str,
    dest_state: str,
    equipment: str,
    pool: asyncpg.Pool,
) -> float:
    """Look up destination market score and estimate likely deadhead after delivery."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT market_score FROM market_scores
            WHERE LOWER(city) = LOWER($1) AND UPPER(state) = UPPER($2)
            """,
            dest_city,
            dest_state,
        )
    if row and row["market_score"] is not None:
        return estimate_deadhead_from_market_score(float(row["market_score"]), equipment)

    # Fallback: neutral market assumption
    return estimate_deadhead_from_market_score(50.0, equipment)


async def get_pickup_coordinates(
    load_origin_lat: Optional[float],
    load_origin_lng: Optional[float],
    origin_city: str,
    origin_state: str,
) -> tuple[float, float]:
    if load_origin_lat is not None and load_origin_lng is not None:
        return load_origin_lat, load_origin_lng
    return geocode_city(origin_city, origin_state)
