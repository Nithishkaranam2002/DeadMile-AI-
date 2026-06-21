"""Carrier fleet profile endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.carrier_db import get_carrier_profile, upsert_carrier_profile
from app.db import get_pool
from shared.carrier_profile import CarrierCostProfile, CarrierCostProfileUpdate

router = APIRouter(prefix="/carrier", tags=["carrier"])


def _carrier_id(request: Request) -> str:
    return getattr(request.state, "carrier_id", None) or "default"


@router.get("/profile", response_model=CarrierCostProfile)
async def read_profile(request: Request) -> CarrierCostProfile:
    pool = await get_pool()
    try:
        return await get_carrier_profile(pool, _carrier_id(request))
    except Exception as exc:
        if "carrier_profiles" in str(exc):
            raise HTTPException(
                status_code=503,
                detail="Carrier profiles not initialized. Run: make db-migrate-prod",
            ) from exc
        raise


@router.put("/profile", response_model=CarrierCostProfile)
async def update_profile(body: CarrierCostProfileUpdate, request: Request) -> CarrierCostProfile:
    pool = await get_pool()
    try:
        return await upsert_carrier_profile(pool, _carrier_id(request), body)
    except Exception as exc:
        if "carrier_profiles" in str(exc):
            raise HTTPException(
                status_code=503,
                detail="Carrier profiles not initialized. Run: make db-migrate-prod",
            ) from exc
        raise
