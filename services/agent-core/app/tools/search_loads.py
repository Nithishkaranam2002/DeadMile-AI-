"""Tool 1: Spatial load search via API gateway."""

from __future__ import annotations

import json
import time
from typing import Optional

from langchain_core.tools import tool

from app.clients import API_GATEWAY_URL, get_json
from app.context import emit


@tool
async def search_loads(
    latitude: float,
    longitude: float,
    radius_miles: int = 250,
    equipment: Optional[str] = None,
    min_rate: Optional[float] = None,
    max_miles: Optional[int] = None,
    commodity: Optional[str] = None,
) -> str:
    """Search for available loads near a location using PostGIS spatial queries."""
    start = time.time()
    await emit("tool_call", {"tool": "search_loads", "params": {"lat": latitude, "lng": longitude, "radius": radius_miles}})

    params: dict = {"lat": latitude, "lng": longitude, "radius": radius_miles}
    if equipment:
        params["equipment"] = equipment
    if min_rate is not None:
        params["min_rate"] = min_rate
    if max_miles is not None:
        params["max_miles"] = max_miles
    if commodity:
        params["commodity"] = commodity

    try:
        data = await get_json(f"{API_GATEWAY_URL}/loads/search", params=params)
        loads = data.get("loads", data) if isinstance(data, dict) else data
        await emit("tool_result", {"tool": "search_loads", "count": len(loads), "duration_ms": int((time.time() - start) * 1000)})
        for load in loads[:3]:
            await emit("load_found", {"load": load})
        return json.dumps(loads[:20], default=str)
    except Exception as exc:
        await emit("tool_result", {"tool": "search_loads", "error": str(exc)})
        return json.dumps({"error": str(exc), "loads": []})
