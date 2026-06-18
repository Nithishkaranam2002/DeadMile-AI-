"""Tool 5: Multi-hop load chain optimizer (beam search)."""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from langchain_core.tools import tool

from app.clients import API_GATEWAY_URL, PROFITABILITY_ENGINE_URL, get_json, post_json
from app.context import emit
from app.geo import haversine_miles


async def _profit_for_load(load_id: str, lat: float, lng: float) -> Optional[dict]:
    try:
        return await post_json(
            f"{PROFITABILITY_ENGINE_URL}/calculate",
            {"load_id": load_id, "driver_lat": lat, "driver_lng": lng},
        )
    except Exception:
        return None


async def _loads_from(lat: float, lng: float, equipment: str, limit: int = 10) -> list[dict]:
    try:
        data = await get_json(
            f"{API_GATEWAY_URL}/loads/search",
            params={"lat": lat, "lng": lng, "radius": 250, "equipment": equipment, "limit": limit},
        )
        return data.get("loads", [])
    except Exception:
        return []


def _score_chain(chain: list[dict], start_lat: float, start_lng: float, prefer_return: bool) -> float:
    total_profit = sum(c.get("net_profit", 0) for c in chain)
    if prefer_return and chain:
        last = chain[-1]
        dest = last.get("destination", "")
        # Penalty for ending far from start (~$2/mile penalty)
        end_lat = last.get("dest_lat") or start_lat
        end_lng = last.get("dest_lng") or start_lng
        dist = haversine_miles(start_lat, start_lng, end_lat, end_lng)
        total_profit -= dist * 2.0
    return total_profit


@tool
async def find_load_chain(
    start_lat: float,
    start_lng: float,
    equipment: str,
    num_hops: int = 3,
    days: int = 5,
    prefer_return_to_start: bool = True,
) -> str:
    """Find optimal sequence of loads maximizing cumulative net profit via beam search."""
    start = time.time()
    num_hops = max(2, min(5, num_hops))
    await emit("tool_call", {"tool": "find_load_chain", "hops": num_hops, "equipment": equipment})

    beam_widths = [10] + [5] * (num_hops - 1)
    beams: list[tuple[list[dict], float, float, float]] = [( [], start_lat, start_lng, 0.0)]

    for hop, width in enumerate(beam_widths):
        next_beams: list[tuple[list[dict], float, float, float]] = []
        for chain, lat, lng, _ in beams:
            candidates = await _loads_from(lat, lng, equipment, limit=width)
            if not candidates and hop == 0:
                return json.dumps({"error": "No loads found for chain", "chains": []})

            for load in candidates:
                profit = await _profit_for_load(load["load_id"], lat, lng)
                if not profit:
                    continue
                profit["dest_lat"] = load.get("dest_lat")
                profit["dest_lng"] = load.get("dest_lng")
                new_chain = chain + [profit]
                dest_lat = load.get("dest_lat") or lat
                dest_lng = load.get("dest_lng") or lng
                score = _score_chain(new_chain, start_lat, start_lng, prefer_return_to_start)
                next_beams.append((new_chain, dest_lat, dest_lng, score))

        if not next_beams:
            break
        next_beams.sort(key=lambda x: x[3], reverse=True)
        beams = next_beams[:width]

    chains = []
    for chain, _, _, score in sorted(beams, key=lambda x: x[3], reverse=True)[:3]:
        chains.append({
            "loads": chain,
            "cumulative_net_profit": round(sum(c.get("net_profit", 0) for c in chain), 2),
            "total_miles": round(sum(c.get("total_miles", 0) for c in chain), 1),
            "estimated_days": min(days, num_hops),
            "score": round(score, 2),
        })

    result = {"chains": chains, "best_chain": chains[0] if chains else None}
    if chains:
        await emit("chain_found", {"chain": chains[0]})
    await emit("tool_result", {"tool": "find_load_chain", "chains_found": len(chains), "duration_ms": int((time.time() - start) * 1000)})
    return json.dumps(result, default=str)
