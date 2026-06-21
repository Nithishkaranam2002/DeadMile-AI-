"""Carrier profile persistence for API gateway."""

from __future__ import annotations

from typing import Optional

import asyncpg

from shared.carrier_profile import CarrierCostProfile, CarrierCostProfileUpdate

_PROFILE_COLUMNS = """
    carrier_id, company_name, default_equipment, max_deadhead_miles,
    fuel_price_per_gallon, avg_mpg_loaded, avg_mpg_empty, driver_cpm,
    insurance_per_mile, maintenance_per_mile, tolls_per_mile,
    dispatch_fee_percent, factoring_fee_percent, overhead_per_mile,
    home_city, home_state
"""


def _row_to_profile(row: asyncpg.Record) -> CarrierCostProfile:
    return CarrierCostProfile(
        carrier_id=row["carrier_id"],
        company_name=row["company_name"],
        default_equipment=row["default_equipment"] or "Dry Van",
        max_deadhead_miles=int(row["max_deadhead_miles"] or 250),
        fuel_price_per_gallon=float(row["fuel_price_per_gallon"] or 3.90),
        avg_mpg_loaded=float(row["avg_mpg_loaded"] or 6.0),
        avg_mpg_empty=float(row["avg_mpg_empty"] or 7.0),
        driver_cpm=float(row["driver_cpm"] or 0.55),
        insurance_per_mile=float(row["insurance_per_mile"] or 0.08),
        maintenance_per_mile=float(row["maintenance_per_mile"] or 0.15),
        tolls_per_mile=float(row["tolls_per_mile"] or 0.04),
        dispatch_fee_percent=float(row["dispatch_fee_percent"] or 0.05),
        factoring_fee_percent=float(row["factoring_fee_percent"] or 0.03),
        overhead_per_mile=float(row["overhead_per_mile"] or 0.05),
        home_city=row["home_city"],
        home_state=row["home_state"],
    )


async def get_carrier_profile(pool: asyncpg.Pool, carrier_id: str = "default") -> CarrierCostProfile:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {_PROFILE_COLUMNS} FROM carrier_profiles WHERE carrier_id = $1",
            carrier_id,
        )
    if not row:
        return CarrierCostProfile(carrier_id=carrier_id)
    return _row_to_profile(row)


async def upsert_carrier_profile(
    pool: asyncpg.Pool,
    carrier_id: str,
    update: CarrierCostProfileUpdate,
) -> CarrierCostProfile:
    current = await get_carrier_profile(pool, carrier_id)
    merged = current.model_copy(update=update.model_dump(exclude_unset=True))

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO carrier_profiles (
                carrier_id, company_name, default_equipment, max_deadhead_miles,
                fuel_price_per_gallon, avg_mpg_loaded, avg_mpg_empty, driver_cpm,
                insurance_per_mile, maintenance_per_mile, tolls_per_mile,
                dispatch_fee_percent, factoring_fee_percent, overhead_per_mile,
                home_city, home_state, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, NOW()
            )
            ON CONFLICT (carrier_id) DO UPDATE SET
                company_name = EXCLUDED.company_name,
                default_equipment = EXCLUDED.default_equipment,
                max_deadhead_miles = EXCLUDED.max_deadhead_miles,
                fuel_price_per_gallon = EXCLUDED.fuel_price_per_gallon,
                avg_mpg_loaded = EXCLUDED.avg_mpg_loaded,
                avg_mpg_empty = EXCLUDED.avg_mpg_empty,
                driver_cpm = EXCLUDED.driver_cpm,
                insurance_per_mile = EXCLUDED.insurance_per_mile,
                maintenance_per_mile = EXCLUDED.maintenance_per_mile,
                tolls_per_mile = EXCLUDED.tolls_per_mile,
                dispatch_fee_percent = EXCLUDED.dispatch_fee_percent,
                factoring_fee_percent = EXCLUDED.factoring_fee_percent,
                overhead_per_mile = EXCLUDED.overhead_per_mile,
                home_city = EXCLUDED.home_city,
                home_state = EXCLUDED.home_state,
                updated_at = NOW()
            """,
            merged.carrier_id,
            merged.company_name,
            merged.default_equipment,
            merged.max_deadhead_miles,
            merged.fuel_price_per_gallon,
            merged.avg_mpg_loaded,
            merged.avg_mpg_empty,
            merged.driver_cpm,
            merged.insurance_per_mile,
            merged.maintenance_per_mile,
            merged.tolls_per_mile,
            merged.dispatch_fee_percent,
            merged.factoring_fee_percent,
            merged.overhead_per_mile,
            merged.home_city,
            merged.home_state,
        )
    return merged


async def log_search_audit(
    pool: asyncpg.Pool,
    carrier_id: str,
    driver_lat: float,
    driver_lng: float,
    equipment: str,
    max_deadhead: int,
    results_count: int,
    top_load_id: Optional[str] = None,
    top_net_profit: Optional[float] = None,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO search_audit (
                carrier_id, driver_lat, driver_lng, equipment, max_deadhead_miles,
                results_count, top_load_id, top_net_profit
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            carrier_id,
            driver_lat,
            driver_lng,
            equipment,
            max_deadhead,
            results_count,
            top_load_id,
            top_net_profit,
        )


async def register_user(pool: asyncpg.Pool, user_id: str, email: str, name: Optional[str] = None) -> bool:
    """Register user if new. Returns True if newly created."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT user_id FROM user_accounts WHERE user_id = $1", user_id[:64])
        if row:
            return False
        await conn.execute(
            "INSERT INTO user_accounts (user_id, email, name) VALUES ($1, $2, $3)",
            user_id[:64],
            email,
            name,
        )
        return True


async def count_registered_users(pool: asyncpg.Pool) -> int:
    async with pool.acquire() as conn:
        val = await conn.fetchval("SELECT COUNT(*) FROM user_accounts")
        return int(val or 0)
