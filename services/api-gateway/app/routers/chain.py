"""Load chain optimization via Temporal or in-process fallback."""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, HTTPException
from temporalio.client import WorkflowFailureError

from app.chain_fallback import optimize_chain_fallback
from app.redis_client import get_redis
from app.schemas import ChainRequest
from app.temporal.models import ChainParams, ChainResult
from app.temporal.worker import get_temporal_client
from app.temporal.workflows import LoadChainWorkflow

router = APIRouter(prefix="/chain", tags=["chain"])

TASK_QUEUE = "load-chain-queue"
RESULT_TTL = 3600


async def _store_result(workflow_id: str, result: dict) -> None:
    redis = await get_redis()
    await redis.setex(f"chain:result:{workflow_id}", RESULT_TTL, json.dumps(result, default=str))


async def _get_stored_result(workflow_id: str) -> dict | None:
    redis = await get_redis()
    raw = await redis.get(f"chain:result:{workflow_id}")
    return json.loads(raw) if raw else None


async def _store_status(workflow_id: str, status: str) -> None:
    redis = await get_redis()
    await redis.setex(f"chain:status:{workflow_id}", RESULT_TTL, status)


async def _get_stored_status(workflow_id: str) -> str | None:
    redis = await get_redis()
    return await redis.get(f"chain:status:{workflow_id}")


async def _cache_workflow_result(workflow_id: str) -> None:
    client = await get_temporal_client()
    if not client:
        return
    try:
        handle = client.get_workflow_handle(workflow_id)
        result: ChainResult = await handle.result()
        payload = {
            "workflow_id": workflow_id,
            "status": "completed",
            "chains": result.chains,
            "total_evaluated": result.total_evaluated,
        }
        await _store_result(workflow_id, payload)
        await _store_status(workflow_id, "completed")
    except Exception:
        await _store_status(workflow_id, "failed")


@router.post("/optimize")
async def optimize_chain(request: ChainRequest) -> dict:
    workflow_id = f"chain-{uuid.uuid4().hex[:12]}"
    params = ChainParams(
        start_lat=request.start_lat,
        start_lng=request.start_lng,
        equipment=request.equipment,
        num_hops=request.num_hops,
        days=request.days,
        prefer_return_to_start=request.prefer_return_to_start,
        driver_id=request.driver_id,
    )

    client = await get_temporal_client()
    if client:
        try:
            await _store_status(workflow_id, "running")
            handle = await client.start_workflow(
                LoadChainWorkflow.run,
                params,
                id=workflow_id,
                task_queue=TASK_QUEUE,
            )
            asyncio.create_task(_cache_workflow_result(handle.id))
            return {
                "workflow_id": handle.id,
                "status": "running",
                "message": "Chain optimization started via Temporal",
            }
        except Exception:
            pass

    await _store_status(workflow_id, "running")
    result = await optimize_chain_fallback(request)
    payload = {
        "workflow_id": workflow_id,
        "status": "completed",
        "chains": result.chains,
        "total_evaluated": result.total_evaluated,
    }
    await _store_result(workflow_id, payload)
    await _store_status(workflow_id, "completed")
    return {
        "workflow_id": workflow_id,
        "status": "completed",
        "chains": result.chains[:3],
        "total_evaluated": result.total_evaluated,
        "message": "Chain optimized in-process (Temporal unavailable)",
    }


@router.get("/status/{workflow_id}")
async def chain_status(workflow_id: str) -> dict:
    stored = await _get_stored_status(workflow_id)
    if stored:
        return {"workflow_id": workflow_id, "status": stored}

    client = await get_temporal_client()
    if client:
        try:
            handle = client.get_workflow_handle(workflow_id)
            desc = await handle.describe()
            status = desc.status.name.lower()
            if status == "completed":
                try:
                    result: ChainResult = await handle.result()
                    await _store_result(workflow_id, {
                        "chains": result.chains,
                        "total_evaluated": result.total_evaluated,
                    })
                except WorkflowFailureError as exc:
                    raise HTTPException(status_code=500, detail=str(exc)) from exc
            return {"workflow_id": workflow_id, "status": status}
        except Exception as exc:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {exc}") from exc

    raise HTTPException(status_code=404, detail="Workflow not found")


@router.get("/result/{workflow_id}")
async def chain_result(workflow_id: str) -> dict:
    stored = await _get_stored_result(workflow_id)
    if stored:
        return stored

    client = await get_temporal_client()
    if client:
        try:
            handle = client.get_workflow_handle(workflow_id)
            result: ChainResult = await handle.result()
            payload = {
                "workflow_id": workflow_id,
                "status": "completed",
                "chains": result.chains,
                "total_evaluated": result.total_evaluated,
            }
            await _store_result(workflow_id, payload)
            return payload
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    raise HTTPException(status_code=404, detail="Result not found")
