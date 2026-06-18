"""Tool 2: Net profitability calculation."""

from __future__ import annotations

import json
import time
from typing import Optional

from langchain_core.tools import tool

from app.clients import PROFITABILITY_ENGINE_URL, post_json
from app.context import emit


@tool
async def calculate_profitability(
    load_id: str,
    driver_lat: float,
    driver_lng: float,
    fuel_price: Optional[float] = None,
) -> str:
    """Calculate TRUE net profitability of a load including all costs."""
    start = time.time()
    await emit("tool_call", {"tool": "calculate_profitability", "load_id": load_id})

    body: dict = {"load_id": load_id, "driver_lat": driver_lat, "driver_lng": driver_lng}
    if fuel_price is not None:
        body["fuel_price_override"] = fuel_price

    try:
        data = await post_json(f"{PROFITABILITY_ENGINE_URL}/calculate", body)
        await emit("tool_result", {
            "tool": "calculate_profitability",
            "load_id": load_id,
            "net_profit": data.get("net_profit"),
            "duration_ms": int((time.time() - start) * 1000),
        })
        await emit("load_found", {"load": data, "type": "profit_breakdown"})
        return json.dumps(data, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc), "load_id": load_id})
