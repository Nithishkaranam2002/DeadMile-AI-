"""Market scoring engine."""

from __future__ import annotations

from datetime import datetime, timezone

import asyncpg
import structlog

from shared import constants as c
from shared.geocoding import geocode_city
from shared.models import MarketScore

logger = structlog.get_logger(__name__)


def _normalize_score(raw: float, min_v: float, max_v: float) -> float:
    if max_v <= min_v:
        return 50.0
    return max(0.0, min(100.0, (raw - min_v) / (max_v - min_v) * 100.0))


class MarketScorer:
    async def compute_all_market_scores(self, pool: asyncpg.Pool) -> list[MarketScore]:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH outbound AS (
                    SELECT origin_city AS city, origin_state AS state,
                           COUNT(*) AS outbound_count,
                           AVG(rate_per_mile) AS avg_outbound_rate,
                           COUNT(DISTINCT equipment) AS equip_diversity
                    FROM loads GROUP BY origin_city, origin_state
                ),
                inbound AS (
                    SELECT dest_city AS city, dest_state AS state,
                           COUNT(*) AS inbound_count,
                           AVG(rate_per_mile) AS avg_inbound_rate
                    FROM loads GROUP BY dest_city, dest_state
                ),
                combined AS (
                    SELECT
                        COALESCE(o.city, i.city) AS city,
                        COALESCE(o.state, i.state) AS state,
                        COALESCE(o.outbound_count, 0) AS outbound_count,
                        COALESCE(i.inbound_count, 0) AS inbound_count,
                        COALESCE(o.avg_outbound_rate, 0) AS avg_outbound_rate,
                        COALESCE(i.avg_inbound_rate, 0) AS avg_inbound_rate,
                        COALESCE(o.equip_diversity, 0) AS equip_diversity
                    FROM outbound o
                    FULL OUTER JOIN inbound i ON o.city = i.city AND o.state = i.state
                )
                SELECT * FROM combined WHERE city IS NOT NULL
                """
            )

        if not rows:
            return []

        max_out = max(r["outbound_count"] for r in rows) or 1
        max_in = max(r["inbound_count"] for r in rows) or 1
        max_rate = max(float(r["avg_outbound_rate"] or 0) for r in rows) or 1.0
        max_equip = max(r["equip_diversity"] for r in rows) or 1

        scores: list[MarketScore] = []
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        async with pool.acquire() as conn:
            for row in rows:
                outbound = int(row["outbound_count"])
                inbound = int(row["inbound_count"])
                avg_out = float(row["avg_outbound_rate"] or 0)
                avg_in = float(row["avg_inbound_rate"] or 0)
                equip_div = int(row["equip_diversity"])
                lane_balance = outbound / max(inbound, 1)

                raw_score = (
                    _normalize_score(outbound, 0, max_out) * 0.35
                    + _normalize_score(avg_out, 0, max_rate) * 0.25
                    + _normalize_score(lane_balance, 0, 5) * 0.20
                    + _normalize_score(equip_div, 0, max_equip) * 0.10
                    + _normalize_score(inbound, 0, max_in) * 0.10
                )
                market_score = round(raw_score, 2)
                label = c.market_label_for_score(market_score)
                lat, lng = geocode_city(row["city"], row["state"])

                ms = MarketScore(
                    city=row["city"],
                    state=row["state"],
                    lat=lat,
                    lng=lng,
                    outbound_load_count=outbound,
                    inbound_load_count=inbound,
                    avg_outbound_rate=round(avg_out, 2),
                    avg_inbound_rate=round(avg_in, 2),
                    lane_balance_ratio=round(lane_balance, 2),
                    market_score=market_score,
                    equipment_diversity=equip_div,
                    label=label,
                )
                scores.append(ms)

                await conn.execute(
                    """
                    INSERT INTO market_scores (
                        city, state, point, outbound_load_count,
                        avg_outbound_rate, avg_inbound_rate,
                        lane_balance_ratio, market_score, updated_at
                    ) VALUES (
                        $1, $2, ST_SetSRID(ST_MakePoint($3, $4), 4326)::geography,
                        $5, $6, $7, $8, $9, $10
                    )
                    ON CONFLICT (city, state) DO UPDATE SET
                        point = EXCLUDED.point,
                        outbound_load_count = EXCLUDED.outbound_load_count,
                        avg_outbound_rate = EXCLUDED.avg_outbound_rate,
                        avg_inbound_rate = EXCLUDED.avg_inbound_rate,
                        lane_balance_ratio = EXCLUDED.lane_balance_ratio,
                        market_score = EXCLUDED.market_score,
                        updated_at = EXCLUDED.updated_at
                    """,
                    ms.city,
                    ms.state,
                    lng,
                    lat,
                    ms.outbound_load_count,
                    ms.avg_outbound_rate,
                    ms.avg_inbound_rate,
                    ms.lane_balance_ratio,
                    ms.market_score,
                    now,
                )

        scores.sort(key=lambda s: s.market_score, reverse=True)
        logger.info("market_scores_computed", count=len(scores))
        return scores

    async def get_top_markets(self, limit: int, pool: asyncpg.Pool) -> list[MarketScore]:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT city, state,
                       ST_Y(point::geometry) AS lat, ST_X(point::geometry) AS lng,
                       outbound_load_count, avg_outbound_rate, avg_inbound_rate,
                       lane_balance_ratio, market_score
                FROM market_scores
                ORDER BY market_score DESC NULLS LAST
                LIMIT $1
                """,
                limit,
            )
        return [
            MarketScore(
                city=r["city"],
                state=r["state"],
                lat=float(r["lat"] or geocode_city(r["city"], r["state"])[0]),
                lng=float(r["lng"] or geocode_city(r["city"], r["state"])[1]),
                outbound_load_count=r["outbound_load_count"] or 0,
                avg_outbound_rate=float(r["avg_outbound_rate"] or 0),
                avg_inbound_rate=float(r["avg_inbound_rate"] or 0),
                lane_balance_ratio=float(r["lane_balance_ratio"] or 0),
                market_score=float(r["market_score"] or 0),
                label=c.market_label_for_score(float(r["market_score"] or 0)),
            )
            for r in rows
        ]

    async def get_market_score(self, city: str, state: str, pool: asyncpg.Pool) -> MarketScore | None:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT city, state,
                       ST_Y(point::geometry) AS lat, ST_X(point::geometry) AS lng,
                       outbound_load_count, avg_outbound_rate, avg_inbound_rate,
                       lane_balance_ratio, market_score
                FROM market_scores
                WHERE LOWER(city) = LOWER($1) AND UPPER(state) = UPPER($2)
                """,
                city,
                state,
            )
        if not row:
            return None
        score = float(row["market_score"] or 0)
        return MarketScore(
            city=row["city"],
            state=row["state"],
            lat=float(row["lat"] or geocode_city(city, state)[0]),
            lng=float(row["lng"] or geocode_city(city, state)[1]),
            outbound_load_count=row["outbound_load_count"] or 0,
            avg_outbound_rate=float(row["avg_outbound_rate"] or 0),
            avg_inbound_rate=float(row["avg_inbound_rate"] or 0),
            lane_balance_ratio=float(row["lane_balance_ratio"] or 0),
            market_score=score,
            label=c.market_label_for_score(score),
        )

    async def get_market_heatmap_data(self, pool: asyncpg.Pool) -> list[dict]:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT city, state,
                       ST_Y(point::geometry) AS lat, ST_X(point::geometry) AS lng,
                       market_score, outbound_load_count, avg_outbound_rate
                FROM market_scores
                WHERE point IS NOT NULL
                ORDER BY market_score DESC
                """
            )
        return [
            {
                "lat": float(r["lat"]),
                "lng": float(r["lng"]),
                "score": float(r["market_score"] or 0),
                "city": r["city"],
                "state": r["state"],
                "load_count": r["outbound_load_count"] or 0,
                "avg_rate": float(r["avg_outbound_rate"] or 0),
            }
            for r in rows
        ]
