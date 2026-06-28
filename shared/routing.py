"""Road distance via OSRM / OpenRouteService with haversine fallback."""

from __future__ import annotations

import logging
import math
import os
from typing import Literal, Optional

import httpx

from shared import constants as c

logger = logging.getLogger(__name__)

RoutingSource = Literal["osrm", "openrouteservice", "haversine"]

ROUTING_PROVIDER = os.getenv("ROUTING_PROVIDER", "osrm").lower().strip()
OSRM_URL = os.getenv("OSRM_URL", "https://router.project-osrm.org").rstrip("/")
OPENROUTESERVICE_API_KEY = os.getenv("OPENROUTESERVICE_API_KEY", "").strip()
ROUTING_TIMEOUT = float(os.getenv("ROUTING_TIMEOUT_SECONDS", "8"))


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 3958.8
    lat1_r, lng1_r, lat2_r, lng2_r = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat = lat2_r - lat1_r
    dlng = lng2_r - lng1_r
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


def haversine_road_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    return haversine_miles(lat1, lng1, lat2, lng2) * c.ROAD_FACTOR


def _cache_key(lat1: float, lng1: float, lat2: float, lng2: float) -> str:
    return f"route:{lat1:.4f},{lng1:.4f}:{lat2:.4f},{lng2:.4f}"


async def _osrm_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> Optional[float]:
    # OSRM expects lon,lat
    url = f"{OSRM_URL}/route/v1/driving/{lng1},{lat1};{lng2},{lat2}"
    params = {"overview": "false", "alternatives": "false", "steps": "false"}
    try:
        async with httpx.AsyncClient(timeout=ROUTING_TIMEOUT) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if data.get("code") != "Ok" or not data.get("routes"):
                return None
            meters = data["routes"][0]["distance"]
            return round(meters / 1609.34, 1)
    except Exception as exc:
        logger.warning("OSRM routing failed: %s", exc)
        return None


async def _ors_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> Optional[float]:
    if not OPENROUTESERVICE_API_KEY:
        return None
    url = "https://api.openrouteservice.org/v2/directions/driving-hgv"
    headers = {"Authorization": OPENROUTESERVICE_API_KEY, "Content-Type": "application/json"}
    body = {"coordinates": [[lng1, lat1], [lng2, lat2]]}
    try:
        async with httpx.AsyncClient(timeout=ROUTING_TIMEOUT) as client:
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code != 200:
                return None
            data = resp.json()
            routes = data.get("routes") or []
            if not routes:
                return None
            meters = routes[0]["summary"]["distance"]
            return round(meters / 1609.34, 1)
    except Exception as exc:
        logger.warning("OpenRouteService routing failed: %s", exc)
        return None


async def road_miles(
    lat1: float,
    lng1: float,
    lat2: float,
    lng2: float,
    *,
    cache: Optional[object] = None,
) -> tuple[float, RoutingSource]:
    """
    Return driving miles between two points.
    Uses Redis cache when provided (CacheManager with get/set for float stored as dict).
    """
    key = _cache_key(lat1, lng1, lat2, lng2)
    if cache is not None:
        try:
            cached = await cache.get(key)
            if cached and "miles" in cached:
                return float(cached["miles"]), cached.get("source", "haversine")  # type: ignore
        except Exception:
            pass

    miles: Optional[float] = None
    source: RoutingSource = "haversine"

    provider = ROUTING_PROVIDER
    if provider == "openrouteservice":
        miles = await _ors_miles(lat1, lng1, lat2, lng2)
        if miles is not None:
            source = "openrouteservice"
    elif provider == "osrm":
        miles = await _osrm_miles(lat1, lng1, lat2, lng2)
        if miles is not None:
            source = "osrm"
    else:
        # auto: try OSRM then ORS
        miles = await _osrm_miles(lat1, lng1, lat2, lng2)
        if miles is not None:
            source = "osrm"
        elif OPENROUTESERVICE_API_KEY:
            miles = await _ors_miles(lat1, lng1, lat2, lng2)
            if miles is not None:
                source = "openrouteservice"

    if miles is None:
        miles = round(haversine_road_miles(lat1, lng1, lat2, lng2), 1)
        source = "haversine"

    if cache is not None:
        try:
            await cache.set(key, {"miles": miles, "source": source}, ttl=86400)
        except Exception:
            pass

    return miles, source
