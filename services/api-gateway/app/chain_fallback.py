"""In-process load chain optimization fallback when Temporal is unavailable."""

from __future__ import annotations

import math
from typing import Any, Optional

import httpx

from app.config import settings
from app.schemas import ChainRequest
from app.temporal.models import ChainResult


def _haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a)) * 1.3


async def _get_json(client: httpx.AsyncClient, url: str, **kwargs) -> dict:
    resp = await client.get(url, **kwargs)
    resp.raise_for_status()
    return resp.json()


async def _post_json(client: httpx.AsyncClient, url: str, body: dict) -> dict:
    resp = await client.post(url, json=body)
    resp.raise_for_status()
    return resp.json()


async def optimize_chain_fallback(request: ChainRequest) -> ChainResult:
    """Beam search chain optimization without Temporal."""
    num_hops = max(2, min(5, request.num_hops))
    beam_widths = [10] + [5] * (num_hops - 1)
    beams: list[tuple[list[dict], float, float, float]] = [( [], request.start_lat, request.start_lng, 0.0)]

    async with httpx.AsyncClient(timeout=30.0) as client:
        for hop, width in enumerate(beam_widths):
            next_beams: list[tuple[list[dict], float, float, float]] = []
            for chain, lat, lng, _ in beams:
                data = await _get_json(
                    client,
                    f"{settings.api_gateway_url}/loads/search",
                    params={"lat": lat, "lng": lng, "radius": 250, "equipment": request.equipment, "limit": width},
                )
                candidates = data.get("loads", [])
                if not candidates and hop == 0:
                    return ChainResult(chains=[], total_evaluated=0)

                for load in candidates:
                    try:
                        profit = await _post_json(
                            client,
                            f"{settings.profitability_engine_url}/calculate",
                            {"load_id": load["load_id"], "driver_lat": lat, "driver_lng": lng},
                        )
                    except Exception:
                        continue
                    profit["dest_lat"] = load.get("dest_lat")
                    profit["dest_lng"] = load.get("dest_lng")
                    new_chain = chain + [profit]
                    dest_lat = load.get("dest_lat") or lat
                    dest_lng = load.get("dest_lng") or lng
                    score = sum(c.get("net_profit", 0) for c in new_chain)
                    if request.prefer_return_to_start:
                        dist = _haversine_miles(request.start_lat, request.start_lng, dest_lat, dest_lng)
                        score -= dist * 2.0
                    next_beams.append((new_chain, dest_lat, dest_lng, score))

            if not next_beams:
                break
            next_beams.sort(key=lambda x: x[3], reverse=True)
            beams = next_beams[:width]

    chains: list[dict[str, Any]] = []
    for chain, _, _, score in sorted(beams, key=lambda x: x[3], reverse=True)[:3]:
        chains.append({
            "loads": chain,
            "hops": [
                {
                    "load_id": l.get("load_id"),
                    "origin": l.get("origin"),
                    "destination": l.get("destination"),
                    "net_profit": l.get("net_profit"),
                    "deadhead_miles": l.get("deadhead_to_pickup", 0),
                    "equipment": l.get("equipment", request.equipment),
                }
                for l in chain
            ],
            "cumulative_net_profit": round(sum(c.get("net_profit", 0) for c in chain), 2),
            "total_miles": round(sum(c.get("total_miles", 0) for c in chain), 1),
            "estimated_days": min(request.days, num_hops),
            "weekly_projection": round(sum(c.get("net_profit", 0) for c in chain) * 1.4, 2),
            "monthly_projection": round(sum(c.get("net_profit", 0) for c in chain) * 5.6, 2),
            "score": round(score, 2),
        })

    return ChainResult(chains=chains, total_evaluated=len(beams))
