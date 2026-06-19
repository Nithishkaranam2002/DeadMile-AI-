"""Health check aggregator."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter

from app.config import settings
from app.proxy import check_health

router = APIRouter(tags=["health"])


@router.get("/health/all")
async def health_all() -> dict:
    services = {
        "api-gateway": "http://localhost:8000/health",
        "agent-core": f"{settings.agent_core_url}/health",
        "profitability-engine": f"{settings.profitability_engine_url}/health",
        "market-intelligence": f"{settings.market_intelligence_url}/health",
        "load-ingestion": f"{settings.load_ingestion_url}/health",
        "load-processor": f"{settings.load_processor_url}/health",
    }

    async def check(name: str, url: str) -> tuple[str, dict]:
        return name, await check_health(url)

    results_list = await asyncio.gather(*[check(n, u) for n, u in services.items()])
    results = dict(results_list)
    all_healthy = all(r["status"] == "healthy" for r in results.values())
    return {"status": "healthy" if all_healthy else "degraded", "services": results}
