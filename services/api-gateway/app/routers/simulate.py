"""What-if simulator and load comparison."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.config import settings
from app.proxy import proxy_json
from app.schemas import CompareRequest, WhatIfRequest

router = APIRouter(prefix="/simulate", tags=["simulate"])


class BatchRequest(BaseModel):
    driver_lat: float
    driver_lng: float
    equipment: str = "Dry Van"
    max_deadhead_miles: int = Field(default=250, ge=0, le=500)
    limit: int = Field(default=20, ge=1, le=100)


@router.post("/what-if")
async def what_if(request: WhatIfRequest, req: Request) -> dict:
    request_id = req.headers.get("X-Request-ID")
    return await proxy_json(
        "POST",
        f"{settings.profitability_engine_url}/calculate/what-if",
        json_body=request.model_dump(),
        timeout=60.0,
        request_id=request_id,
    )


@router.post("/batch")
async def batch_calculate(request: BatchRequest, req: Request) -> list:
    request_id = req.headers.get("X-Request-ID")
    return await proxy_json(
        "POST",
        f"{settings.profitability_engine_url}/calculate/batch",
        json_body=request.model_dump(),
        timeout=60.0,
        request_id=request_id,
    )


@router.post("/compare")
async def compare_loads(request: CompareRequest, req: Request) -> dict:
    """Compare 2-3 loads with profitability + market scores."""
    request_id = req.headers.get("X-Request-ID")

    async def calc_one(load_id: str) -> dict:
        profit = await proxy_json(
            "POST",
            f"{settings.profitability_engine_url}/calculate",
            json_body={
                "load_id": load_id,
                "driver_lat": request.driver_lat,
                "driver_lng": request.driver_lng,
            },
            timeout=30.0,
            request_id=request_id,
        )
        dest_parts = profit.get("destination", "").split(",")
        dest_city = dest_parts[0].strip() if dest_parts else ""
        dest_state = dest_parts[1].strip() if len(dest_parts) > 1 else ""
        market = {}
        if dest_city and dest_state:
            try:
                market = await proxy_json(
                    "GET",
                    f"{settings.market_intelligence_url}/markets/{dest_city}/{dest_state}",
                    request_id=request_id,
                )
            except Exception:
                market = {}
        return {"load_id": load_id, "profit": profit, "market": market}

    results = await asyncio.gather(*[calc_one(lid) for lid in request.load_ids])
    return {"comparisons": results, "count": len(results)}
