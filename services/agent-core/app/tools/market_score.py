"""Tool 3: Destination market quality score."""

from __future__ import annotations

import json
import time

from langchain_core.tools import tool

from app.clients import MARKET_INTELLIGENCE_URL, get_json
from app.context import emit


@tool
async def get_market_score(city: str, state: str) -> str:
    """Get market quality score for a destination city (Hot/Warm/Neutral/Cool/Dead)."""
    start = time.time()
    await emit("tool_call", {"tool": "get_market_score", "city": city, "state": state})

    try:
        data = await get_json(f"{MARKET_INTELLIGENCE_URL}/markets/{city}/{state}")
        await emit("market_data", {"market": data})
        await emit("tool_result", {"tool": "get_market_score", "score": data.get("market_score"), "duration_ms": int((time.time() - start) * 1000)})
        return json.dumps(data, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc), "city": city, "state": state, "market_score": 50, "label": "Unknown"})
