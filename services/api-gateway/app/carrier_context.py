"""Load carrier cost overrides for profitability requests."""

from __future__ import annotations

from fastapi import Request

from app.carrier_db import get_carrier_profile
from app.db import get_pool


async def get_cost_overrides(request: Request) -> dict:
    carrier_id = getattr(request.state, "carrier_id", None) or "default"
    try:
        pool = await get_pool()
        profile = await get_carrier_profile(pool, carrier_id)
        return profile.to_cost_overrides()
    except Exception:
        return {}
