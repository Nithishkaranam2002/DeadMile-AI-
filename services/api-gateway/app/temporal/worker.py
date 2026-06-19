"""Temporal worker for load chain workflows."""

from __future__ import annotations

import asyncio
import logging
import os

from temporalio.client import Client
from temporalio.worker import Worker

from app.temporal.activities import (
    calculate_profit_activity,
    score_chains_activity,
    search_loads_activity,
)
from app.temporal.workflows import LoadChainWorkflow

logger = logging.getLogger(__name__)

_worker_task: asyncio.Task | None = None


async def start_temporal_worker() -> bool:
    """Start Temporal worker as background task. Returns True if connected."""
    global _worker_task
    address = os.getenv("TEMPORAL_ADDRESS", "temporal:7233")
    task_queue = os.getenv("TEMPORAL_TASK_QUEUE", "load-chain-queue")

    try:
        client = await Client.connect(address)
        worker = Worker(
            client,
            task_queue=task_queue,
            workflows=[LoadChainWorkflow],
            activities=[
                search_loads_activity,
                calculate_profit_activity,
                score_chains_activity,
            ],
        )
        _worker_task = asyncio.create_task(worker.run())
        logger.info("Temporal worker started on %s queue=%s", address, task_queue)
        return True
    except Exception as exc:
        logger.warning("Temporal unavailable, using in-process chain fallback: %s", exc)
        return False


async def stop_temporal_worker() -> None:
    global _worker_task
    if _worker_task is not None:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None


async def get_temporal_client() -> Client | None:
    address = os.getenv("TEMPORAL_ADDRESS", "temporal:7233")
    try:
        return await Client.connect(address)
    except Exception:
        return None
