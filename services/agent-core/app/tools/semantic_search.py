"""Tool 7: Semantic load search via Qdrant."""

from __future__ import annotations

import json
import time
from typing import Optional

from langchain_core.tools import tool

from app.context import emit
from app.qdrant_setup import QdrantSeeder


@tool
async def semantic_load_search(
    query: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    limit: int = 10,
) -> str:
    """Search loads using natural language semantic matching on commodities."""
    start = time.time()
    await emit("tool_call", {"tool": "semantic_load_search", "query": query})

    try:
        seeder = QdrantSeeder()
        results = await seeder.search(query, limit=limit, lat=latitude, lng=longitude)
        await emit("tool_result", {"tool": "semantic_load_search", "count": len(results), "duration_ms": int((time.time() - start) * 1000)})
        for r in results[:3]:
            await emit("load_found", {"load": r, "source": "semantic"})
        return json.dumps(results, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc), "results": [], "note": "Semantic search unavailable — try search_loads instead"})
