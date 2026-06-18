"""Tool 8: Driver preferences from Mem0."""

from __future__ import annotations

import json
import time

from langchain_core.tools import tool

from app.context import emit
from app.memory import DriverMemory

_memory = DriverMemory()


@tool
async def get_driver_preferences(driver_id: str) -> str:
    """Retrieve stored driver preferences and history from memory."""
    start = time.time()
    await emit("tool_call", {"tool": "get_driver_preferences", "driver_id": driver_id})

    prefs = await _memory.get_preferences(driver_id)
    await emit("tool_result", {"tool": "get_driver_preferences", "duration_ms": int((time.time() - start) * 1000)})
    return json.dumps(prefs, default=str)
