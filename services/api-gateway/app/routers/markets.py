"""Market intelligence proxy."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.config import settings
from app.proxy import proxy_json
from app.schemas import RatePredictRequest

router = APIRouter(tags=["markets"])


@router.get("/markets/top")
async def top_markets(limit: int = 10, req: Request = ...) -> list:
    request_id = req.headers.get("X-Request-ID")
    return await proxy_json(
        "GET",
        f"{settings.market_intelligence_url}/markets/top",
        params={"limit": limit},
        request_id=request_id,
    )


@router.get("/markets/heatmap")
async def market_heatmap(req: Request = ...) -> list:
    request_id = req.headers.get("X-Request-ID")
    return await proxy_json(
        "GET",
        f"{settings.market_intelligence_url}/markets/heatmap",
        request_id=request_id,
    )


@router.get("/markets/clusters")
async def market_clusters(req: Request = ...) -> list:
    request_id = req.headers.get("X-Request-ID")
    return await proxy_json(
        "GET",
        f"{settings.market_intelligence_url}/markets/clusters",
        request_id=request_id,
    )


@router.get("/markets/{city}/{state}")
async def market_detail(city: str, state: str, req: Request = ...) -> dict:
    request_id = req.headers.get("X-Request-ID")
    return await proxy_json(
        "GET",
        f"{settings.market_intelligence_url}/markets/{city}/{state}",
        request_id=request_id,
    )


@router.post("/rates/predict")
async def predict_rate(request: RatePredictRequest, req: Request) -> dict:
    request_id = req.headers.get("X-Request-ID")
    return await proxy_json(
        "POST",
        f"{settings.market_intelligence_url}/rates/predict",
        json_body=request.model_dump(),
        request_id=request_id,
    )


@router.get("/rates/history/{origin_state}/{dest_state}")
async def rate_history(origin_state: str, dest_state: str, req: Request = ...) -> dict:
    request_id = req.headers.get("X-Request-ID")
    return await proxy_json(
        "GET",
        f"{settings.market_intelligence_url}/rates/history/{origin_state}/{dest_state}",
        request_id=request_id,
    )
