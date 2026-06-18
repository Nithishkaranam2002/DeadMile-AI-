"""Rate history aggregation for TimescaleDB hypertable."""

from __future__ import annotations

from datetime import datetime, timezone

import structlog

from app.db import get_pool

logger = structlog.get_logger(__name__)


async def populate_rate_history() -> int:
    """Aggregate lane rates by equipment and insert into rate_history."""
    pool = await get_pool()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                origin_city, origin_state,
                dest_city, dest_state,
                equipment,
                AVG(rate_per_mile) AS avg_rate_per_mile,
                COUNT(*) AS load_count
            FROM loads
            WHERE rate_per_mile > 0
            GROUP BY origin_city, origin_state, dest_city, dest_state, equipment
            """
        )

        inserted = 0
        for row in rows:
            await conn.execute(
                """
                INSERT INTO rate_history (
                    time, origin_city, origin_state,
                    dest_city, dest_state, equipment,
                    avg_rate_per_mile, load_count
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                now,
                row["origin_city"],
                row["origin_state"],
                row["dest_city"],
                row["dest_state"],
                row["equipment"],
                float(row["avg_rate_per_mile"]),
                row["load_count"],
            )
            inserted += 1

    logger.info("rate_history_populated", lanes=inserted)
    return inserted
