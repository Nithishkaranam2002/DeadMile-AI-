"""Resolve real road miles for profitability calculations."""

from __future__ import annotations

import os

from shared.routing import road_miles

from app.deadhead import road_distance_estimate

_cache = None


def get_routing_cache():
    global _cache
    return _cache


def set_routing_cache(cache) -> None:
    global _cache
    _cache = cache


async def deadhead_road_miles(
    lat1: float, lng1: float, lat2: float, lng2: float
) -> tuple[float, str]:
    if os.getenv("ROUTING_ENABLED", "true").lower() in ("0", "false", "no"):
        return round(road_distance_estimate(lat1, lng1, lat2, lng2), 1), "haversine"
    miles, source = await road_miles(lat1, lng1, lat2, lng2, cache=get_routing_cache())
    return miles, source


async def loaded_lane_miles(
    lat1: float, lng1: float, lat2: float, lng2: float, board_miles: int
) -> tuple[int, str]:
    """Use OSRM for loaded lane when RECALC_LOADED_MILES=true, else board miles."""
    if os.getenv("RECALC_LOADED_MILES", "false").lower() not in ("1", "true", "yes"):
        return board_miles, "board"
    miles, source = await deadhead_road_miles(lat1, lng1, lat2, lng2)
    return max(1, int(miles)), source
