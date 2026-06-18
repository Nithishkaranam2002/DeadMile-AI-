"""Tool 6: Real-time diesel fuel prices via Tavily."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Optional

from langchain_core.tools import tool

from app.context import emit
from shared.cache import CacheManager
from shared.config import settings
from shared.constants import FUEL_PRICE_PER_GALLON

_cache: Optional[CacheManager] = None


def _get_cache() -> CacheManager:
    global _cache
    if _cache is None:
        _cache = CacheManager(settings.redis_url)
    return _cache


def _parse_price(text: str) -> Optional[float]:
    matches = re.findall(r"\$?(\d+\.\d{2})", text)
    for m in matches:
        val = float(m)
        if 2.0 < val < 8.0:
            return val
    return None


@tool
async def get_fuel_prices(state: Optional[str] = None, region: Optional[str] = None) -> str:
    """Get current diesel fuel prices using Tavily web search."""
    start = time.time()
    cache_key = f"fuel:{state or region or 'national'}"
    cache = _get_cache()
    await cache.connect()
    cached = await cache.get(cache_key)
    if cached:
        return json.dumps(cached)

    await emit("tool_call", {"tool": "get_fuel_prices", "state": state, "region": region})

    query_target = state or region or "national average"
    api_key = os.getenv("TAVILY_API_KEY", "")

    if api_key:
        try:
            from tavily import TavilyClient

            client = TavilyClient(api_key=api_key)
            result = client.search(
                query=f"current diesel fuel price per gallon {query_target} United States 2026",
                max_results=3,
            )
            for item in result.get("results", []):
                price = _parse_price(item.get("content", ""))
                if price:
                    data = {
                        "diesel_price_per_gallon": price,
                        "source": "tavily",
                        "state": state,
                        "region": region,
                        "national_average": price if not state else FUEL_PRICE_PER_GALLON,
                    }
                    await cache.set(cache_key, data, ttl=21600)
                    await emit("tool_result", {"tool": "get_fuel_prices", "price": price, "duration_ms": int((time.time() - start) * 1000)})
                    return json.dumps(data)
        except Exception as exc:
            await emit("thinking", {"message": f"Tavily unavailable, using default fuel price: {exc}"})

    data = {
        "diesel_price_per_gallon": FUEL_PRICE_PER_GALLON,
        "source": "default",
        "state": state,
        "region": region,
        "national_average": FUEL_PRICE_PER_GALLON,
    }
    return json.dumps(data)
