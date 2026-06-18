"""Tool 4: Lane rate prediction."""

from __future__ import annotations

import json
import time

from langchain_core.tools import tool

from app.clients import MARKET_INTELLIGENCE_URL, post_json
from app.context import emit


@tool
async def predict_lane_rate(
    origin_city: str,
    origin_state: str,
    dest_city: str,
    dest_state: str,
    equipment: str = "Dry Van",
) -> str:
    """Predict rate trend for a freight lane with confidence interval."""
    start = time.time()
    await emit("tool_call", {"tool": "predict_lane_rate", "origin": f"{origin_city}, {origin_state}", "dest": f"{dest_city}, {dest_state}"})

    body = {
        "origin_city": origin_city,
        "origin_state": origin_state,
        "dest_city": dest_city,
        "dest_state": dest_state,
        "equipment": equipment,
    }
    try:
        data = await post_json(f"{MARKET_INTELLIGENCE_URL}/rates/predict", body)
        await emit("tool_result", {"tool": "predict_lane_rate", "trend": data.get("trend"), "duration_ms": int((time.time() - start) * 1000)})
        return json.dumps(data, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})
