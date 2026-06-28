"""Live load feed — upsert loads from broker APIs or webhooks."""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.db import get_pool
from shared.load_upsert import normalize_live_load, upsert_loads
from shared.models import LoadRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/loads/live", tags=["live-feed"])

LIVE_LOAD_API_URL = os.getenv("LIVE_LOAD_API_URL", "").strip()
LIVE_LOAD_API_KEY = os.getenv("LIVE_LOAD_API_KEY", "").strip()
LIVE_LOAD_WEBHOOK_SECRET = os.getenv("LIVE_LOAD_WEBHOOK_SECRET", "").strip()


class LiveLoadBatch(BaseModel):
    loads: list[dict[str, Any]] = Field(..., min_length=1)
    source: str = "live"


class SyncResponse(BaseModel):
    received: int
    upserted: int
    source: str


async def _log_sync(
    source: str,
    received: int,
    upserted: int,
    status: str = "ok",
    error: Optional[str] = None,
) -> None:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO live_sync_log (source, loads_received, loads_upserted, status, error_message)
                VALUES ($1, $2, $3, $4, $5)
                """,
                source,
                received,
                upserted,
                status,
                error,
            )
    except Exception as exc:
        logger.warning("live_sync_log failed: %s", exc)


def _parse_batch(raw_loads: list[dict[str, Any]], source: str) -> list[LoadRecord]:
    records: list[LoadRecord] = []
    for raw in raw_loads:
        record = normalize_live_load(raw, source=source)
        if record:
            records.append(record)
    return records


@router.post("/upsert", response_model=SyncResponse)
async def upsert_live_loads(body: LiveLoadBatch, request: Request) -> SyncResponse:
    """
    Upsert loads from a broker API, cron job, or manual JSON POST.
    Each load needs: load_id, origin_city/state, dest_city/state, miles, rate.
    """
    if LIVE_LOAD_WEBHOOK_SECRET:
        secret = request.headers.get("X-Webhook-Secret") or request.headers.get("x-webhook-secret")
        if secret != LIVE_LOAD_WEBHOOK_SECRET:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")

    records = _parse_batch(body.loads, body.source)
    if not records:
        raise HTTPException(status_code=422, detail="No valid loads in payload")

    pool = await get_pool()
    try:
        count = await upsert_loads(pool, records)
    except Exception as exc:
        await _log_sync(body.source, len(body.loads), 0, "error", str(exc))
        raise HTTPException(status_code=500, detail=f"Upsert failed: {exc}") from exc

    await _log_sync(body.source, len(body.loads), count)
    return SyncResponse(received=len(body.loads), upserted=count, source=body.source)


@router.post("/sync", response_model=SyncResponse)
async def sync_from_configured_api() -> SyncResponse:
    """
    Pull loads from LIVE_LOAD_API_URL (configure in .env).
    Expects JSON: {"loads": [...]} or a top-level array.
    """
    if not LIVE_LOAD_API_URL:
        raise HTTPException(
            status_code=503,
            detail="LIVE_LOAD_API_URL not configured. Set in .env or POST to /loads/live/upsert directly.",
        )

    headers: dict[str, str] = {"Accept": "application/json"}
    if LIVE_LOAD_API_KEY:
        headers["Authorization"] = f"Bearer {LIVE_LOAD_API_KEY}"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(LIVE_LOAD_API_URL, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        await _log_sync("api_sync", 0, 0, "error", str(exc))
        raise HTTPException(status_code=502, detail=f"Live feed fetch failed: {exc}") from exc

    raw_loads = data if isinstance(data, list) else data.get("loads") or data.get("data") or []
    if not isinstance(raw_loads, list):
        raise HTTPException(status_code=502, detail="Unexpected API response format")

    records = _parse_batch(raw_loads, source="api_sync")
    if not records:
        await _log_sync("api_sync", len(raw_loads), 0, "error", "No parseable loads")
        raise HTTPException(status_code=422, detail="API returned no parseable loads")

    pool = await get_pool()
    count = await upsert_loads(pool, records)
    await _log_sync("api_sync", len(raw_loads), count)
    return SyncResponse(received=len(raw_loads), upserted=count, source="api_sync")


@router.get("/status")
async def live_feed_status() -> dict[str, Any]:
    pool = await get_pool()
    total = 0
    last_sync = None
    try:
        async with pool.acquire() as conn:
            total = int(await conn.fetchval("SELECT COUNT(*) FROM loads WHERE source LIKE 'live%' OR source = 'api_sync'") or 0)
            row = await conn.fetchrow(
                "SELECT source, loads_upserted, status, synced_at FROM live_sync_log ORDER BY synced_at DESC LIMIT 1"
            )
            if row:
                last_sync = {
                    "source": row["source"],
                    "loads_upserted": row["loads_upserted"],
                    "status": row["status"],
                    "synced_at": row["synced_at"].isoformat() if row["synced_at"] else None,
                }
    except Exception:
        pass

    return {
        "configured": bool(LIVE_LOAD_API_URL),
        "api_url_set": bool(LIVE_LOAD_API_URL),
        "webhook_secret_set": bool(LIVE_LOAD_WEBHOOK_SECRET),
        "live_loads_in_db": total,
        "last_sync": last_sync,
    }
