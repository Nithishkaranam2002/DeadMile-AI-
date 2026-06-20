"""Batch profitability calculations."""

from __future__ import annotations

from typing import Optional

import httpx
import structlog

from shared.config import settings
from shared.models import ProfitBreakdown

from app.calculator import ProfitabilityCalculator
from app.db import get_loads_by_equipment, get_loads_near_driver, get_market_score, get_pool
from app.deadhead import estimate_post_delivery_deadhead

logger = structlog.get_logger(__name__)


class BatchCalculator:
    def __init__(self, calculator: ProfitabilityCalculator | None = None) -> None:
        self.calculator = calculator or ProfitabilityCalculator()

    async def _fetch_market_score(self, city: str, state: str) -> Optional[float]:
        score = await get_market_score(city, state)
        if score is not None:
            return score
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{settings.market_intelligence_url}/markets/{city}/{state}"
                )
                if resp.status_code == 200:
                    return float(resp.json().get("market_score", 50))
        except Exception as exc:
            logger.warning("market_score_fetch_failed", city=city, state=state, error=str(exc))
        return None

    async def calculate_top_loads(
        self,
        driver_lat: float,
        driver_lng: float,
        equipment: str,
        max_deadhead_miles: int = 250,
        limit: int = 20,
        fuel_price_override: Optional[float] = None,
    ) -> list[ProfitBreakdown]:
        loads = await get_loads_near_driver(
            driver_lat, driver_lng, equipment, max_deadhead_miles, limit=limit * 3
        )

        results: list[ProfitBreakdown] = []
        pool = await get_pool()

        for load in loads:
            dest_city = load.dest_city.strip()
            dest_state = load.dest_state.strip().upper()
            dest_score = await self._fetch_market_score(dest_city, dest_state)
            deadhead_from = await estimate_post_delivery_deadhead(
                dest_city, dest_state, load.equipment, pool
            )
            breakdown = self.calculator.calculate(
                load,
                driver_lat,
                driver_lng,
                fuel_price_override=fuel_price_override,
                destination_market_score=dest_score,
                deadhead_from_delivery=deadhead_from,
            )
            if breakdown.deadhead_to_pickup <= max_deadhead_miles:
                results.append(breakdown)

        results.sort(key=lambda x: x.composite_score, reverse=True)
        return results[:limit]

    async def calculate_all_from_location(
        self,
        lat: float,
        lng: float,
        equipment: Optional[str] = None,
        fuel_price_override: Optional[float] = None,
    ) -> dict:
        """What-if simulator summary for a location."""
        eq = equipment or "Dry Van"
        breakdowns = await self.calculate_top_loads(
            lat, lng, eq, max_deadhead_miles=250, limit=50, fuel_price_override=fuel_price_override
        )

        if not breakdowns:
            all_loads = await get_loads_by_equipment(eq, limit=100)
            pool = await get_pool()
            for load in all_loads[:50]:
                dest_city = load.dest_city.strip()
                dest_state = load.dest_state.strip().upper()
                dest_score = await self._fetch_market_score(dest_city, dest_state)
                deadhead_from = await estimate_post_delivery_deadhead(
                    dest_city, dest_state, load.equipment, pool
                )
                breakdowns.append(
                    self.calculator.calculate(
                        load, lat, lng,
                        fuel_price_override=fuel_price_override,
                        destination_market_score=dest_score,
                        deadhead_from_delivery=deadhead_from,
                    )
                )

        if not breakdowns:
            return {
                "available_loads_count": 0,
                "avg_net_profit": 0.0,
                "best_load_net_profit": 0.0,
                "avg_market_score_of_destinations": 0.0,
                "estimated_weekly_earnings": 0.0,
                "top_loads": [],
            }

        net_profits = [b.net_profit for b in breakdowns]
        market_scores = [b.destination_market_score or 50.0 for b in breakdowns]
        avg_net = sum(net_profits) / len(net_profits)

        return {
            "available_loads_count": len(breakdowns),
            "avg_net_profit": round(avg_net, 2),
            "best_load_net_profit": round(max(net_profits), 2),
            "avg_market_score_of_destinations": round(sum(market_scores) / len(market_scores), 2),
            "estimated_weekly_earnings": round(avg_net * 2.5, 2),
            "top_loads": [b.model_dump() for b in breakdowns[:5]],
        }
