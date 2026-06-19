"""Temporal activities for load chain optimization."""

from __future__ import annotations

import math
import os
from typing import Any

import httpx
from temporalio import activity

API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://api-gateway:8000")
PROFITABILITY_ENGINE_URL = os.getenv("PROFITABILITY_ENGINE_URL", "http://profitability-engine:8004")
MARKET_INTELLIGENCE_URL = os.getenv("MARKET_INTELLIGENCE_URL", "http://market-intelligence:8005")


def _haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a)) * 1.3


@activity.defn
async def search_loads_activity(lat: float, lng: float, equipment: str, radius: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{API_GATEWAY_URL}/loads/search",
            params={"lat": lat, "lng": lng, "radius": radius, "equipment": equipment, "limit": 20},
        )
        resp.raise_for_status()
        return resp.json().get("loads", [])


@activity.defn
async def calculate_profit_activity(load_id: str, driver_lat: float, driver_lng: float) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{PROFITABILITY_ENGINE_URL}/calculate",
            json={"load_id": load_id, "driver_lat": driver_lat, "driver_lng": driver_lng},
        )
        resp.raise_for_status()
        return resp.json()


@activity.defn
async def score_chains_activity(
    chains: list[dict],
    start_lat: float,
    start_lng: float,
    prefer_return: bool,
) -> list[dict]:
    scored = []
    for chain in chains:
        loads = chain.get("loads", [])
        total_profit = sum(l.get("net_profit", 0) for l in loads)
        total_miles = sum(l.get("total_miles", 0) for l in loads) or 1
        avg_rpm = total_profit / total_miles
        market_scores = [l.get("destination_market_score", 50) or 50 for l in loads]
        avg_market = sum(market_scores) / len(market_scores) if market_scores else 50

        return_penalty = 0.0
        if prefer_return and loads:
            last = loads[-1]
            end_lat = last.get("dest_lat") or start_lat
            end_lng = last.get("dest_lng") or start_lng
            dist = _haversine_miles(start_lat, start_lng, end_lat, end_lng)
            return_penalty = min(100, dist / 10)

        composite = (
            (total_profit / 2000) * 50
            + (avg_rpm / 2) * 20
            + (avg_market / 100) * 15
            + (100 - return_penalty) * 0.15
        )

        scored.append({
            **chain,
            "score": round(composite, 2),
            "cumulative_net_profit": round(total_profit, 2),
            "total_miles": round(total_miles, 1),
        })

    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored
