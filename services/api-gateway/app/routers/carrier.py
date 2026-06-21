"""Carrier fleet profile endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from pydantic import BaseModel

from app.carrier_db import get_carrier_profile, upsert_carrier_profile, register_user, count_registered_users
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


class RegisterUserRequest(BaseModel):
    user_id: str
    email: str
    name: str | None = None


@router.post("/register")
async def register_user_account(body: RegisterUserRequest, request: Request) -> dict:
    """Track a new driver signup (called after first login)."""
    pool = await get_pool()
    carrier_id = _carrier_id(request)
    if carrier_id == "default" and body.user_id:
        carrier_id = body.user_id[:64]
    try:
        created = await register_user(pool, body.user_id[:64], str(body.email), body.name)
        if created:
            await upsert_carrier_profile(
                pool,
                carrier_id,
                CarrierCostProfileUpdate(company_name=body.name or "My Fleet"),
            )
        count = await count_registered_users(pool)
        return {"created": created, "driver_count": count}
    except Exception as exc:
        if "user_accounts" in str(exc):
            return {"created": False, "driver_count": 0}
        raise


@router.get("/stats/drivers")
async def driver_stats() -> dict:
    """Public driver signup count for landing page."""
    pool = await get_pool()
    try:
        count = await count_registered_users(pool)
    except Exception:
        count = 0
    return {"count": count}
