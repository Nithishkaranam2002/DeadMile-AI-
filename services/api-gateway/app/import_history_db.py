"""Persist and retrieve saved load import analyses."""

from __future__ import annotations

import json
from typing import Any, Optional

import asyncpg


async def save_import_history(
    pool: asyncpg.Pool,
    carrier_id: str,
    driver_city: Optional[str],
    driver_state: Optional[str],
    equipment: str,
    parsed_count: int,
    insight: str,
    loads: list[dict[str, Any]],
    raw_preview: Optional[str] = None,
) -> int:
    preview = (raw_preview or "")[:500]
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO import_history (
                carrier_id, driver_city, driver_state, equipment,
                parsed_count, insight, loads_json, raw_preview
            ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
            RETURNING id
            """,
            carrier_id[:64],
            driver_city,
            driver_state,
            equipment,
            parsed_count,
            insight,
            json.dumps(loads),
            preview,
        )
    return int(row["id"])


async def list_import_history(pool: asyncpg.Pool, carrier_id: str, limit: int = 20) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, driver_city, driver_state, equipment, parsed_count,
                   insight, loads_json, raw_preview, created_at
            FROM import_history
            WHERE carrier_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            carrier_id[:64],
            min(limit, 50),
        )
    return [_row_summary(r) for r in rows]


async def get_import_history(pool: asyncpg.Pool, carrier_id: str, history_id: int) -> Optional[dict[str, Any]]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, driver_city, driver_state, equipment, parsed_count,
                   insight, loads_json, raw_preview, created_at
            FROM import_history
            WHERE carrier_id = $1 AND id = $2
            """,
            carrier_id[:64],
            history_id,
        )
    if not row:
        return None
    return _row_full(row)


def _row_summary(row: asyncpg.Record) -> dict[str, Any]:
    loads = row["loads_json"]
    if isinstance(loads, str):
        loads = json.loads(loads)
    top = loads[0] if loads else {}
    return {
        "id": row["id"],
        "driver_city": row["driver_city"],
        "driver_state": row["driver_state"],
        "equipment": row["equipment"],
        "parsed_count": row["parsed_count"],
        "insight": row["insight"],
        "top_load": f"{top.get('origin', '?')} → {top.get('destination', '?')}" if top else None,
        "top_net_profit": top.get("net_profit"),
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


def _row_full(row: asyncpg.Record) -> dict[str, Any]:
    loads = row["loads_json"]
    if isinstance(loads, str):
        loads = json.loads(loads)
    return {
        "id": row["id"],
        "driver_city": row["driver_city"],
        "driver_state": row["driver_state"],
        "equipment": row["equipment"],
        "parsed_count": row["parsed_count"],
        "insight": row["insight"],
        "loads": loads,
        "raw_preview": row["raw_preview"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }
