"""Core net profitability calculator."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from shared import constants as c
from shared.cost_settings import CostSettings, cost_settings
from shared.models import (
    DeadheadInfo,
    FeesBreakdown,
    FuelBreakdown,
    LoadRecord,
    ProfitBreakdown,
)

from app.deadhead import estimate_deadhead_from_market_score, road_distance_estimate


def _format_window(start: Optional[datetime], end: Optional[datetime]) -> Optional[str]:
    if not start:
        return None
    if end:
        return f"{start.strftime('%Y-%m-%d %H:%M')} – {end.strftime('%Y-%m-%d %H:%M')}"
    return start.strftime("%Y-%m-%d %H:%M")


def _normalize(value: float, min_val: float, max_val: float) -> float:
    if max_val <= min_val:
        return 50.0
    return max(0.0, min(100.0, (value - min_val) / (max_val - min_val) * 100.0))


class ProfitabilityCalculator:
    """Calculates true net profitability for trucking loads."""

    def __init__(self, settings: CostSettings | None = None) -> None:
        self.settings = settings or cost_settings

    def calculate_deadhead_to_pickup(
        self,
        driver_lat: float,
        driver_lng: float,
        pickup_lat: float,
        pickup_lng: float,
        equipment: str,
        fuel_price: float,
    ) -> DeadheadInfo:
        miles = road_distance_estimate(driver_lat, driver_lng, pickup_lat, pickup_lng)
        fuel_mod = c.EQUIPMENT_FUEL_MODIFIER.get(equipment, 1.0)
        gallons = (miles / self.settings.avg_mpg_empty) * fuel_mod
        fuel_cost = gallons * fuel_price
        driver_cost = miles * self.settings.driver_cpm
        return DeadheadInfo(
            miles=round(miles, 1),
            fuel_cost=round(fuel_cost, 2),
            driver_cost=round(driver_cost, 2),
            total_cost=round(fuel_cost + driver_cost, 2),
        )

    def estimate_deadhead_from_delivery(
        self,
        dest_city: str,
        dest_state: str,
        dest_lat: float,
        dest_lng: float,
        equipment: str,
        destination_market_score: Optional[float] = None,
    ) -> float:
        score = destination_market_score if destination_market_score is not None else 50.0
        return estimate_deadhead_from_market_score(score, equipment)

    def calculate_fuel_cost(
        self,
        loaded_miles: int,
        deadhead_miles_to: float,
        deadhead_miles_from: float,
        equipment: str,
        fuel_price: float,
    ) -> FuelBreakdown:
        fuel_mod = c.EQUIPMENT_FUEL_MODIFIER.get(equipment, 1.0)
        loaded_gallons = (loaded_miles / self.settings.avg_mpg_loaded) * fuel_mod
        deadhead_to_gallons = (deadhead_miles_to / self.settings.avg_mpg_empty) * fuel_mod
        deadhead_from_gallons = (deadhead_miles_from / self.settings.avg_mpg_empty) * fuel_mod

        loaded_fuel = loaded_gallons * fuel_price
        deadhead_to_fuel = deadhead_to_gallons * fuel_price
        deadhead_from_fuel = deadhead_from_gallons * fuel_price

        return FuelBreakdown(
            loaded_fuel=round(loaded_fuel, 2),
            deadhead_to_fuel=round(deadhead_to_fuel, 2),
            deadhead_from_fuel=round(deadhead_from_fuel, 2),
            total_fuel=round(loaded_fuel + deadhead_to_fuel + deadhead_from_fuel, 2),
        )

    def calculate_driver_cost(self, total_miles: float, requirements: Optional[str]) -> float:
        cost = total_miles * self.settings.driver_cpm
        if requirements and requirements.lower() == "team":
            cost *= self.settings.team_driver_multiplier
        return round(cost, 2)

    def calculate_fees(self, gross_rate: float) -> FeesBreakdown:
        dispatch = gross_rate * self.settings.dispatch_fee_percent
        factoring = gross_rate * self.settings.factoring_fee_percent
        return FeesBreakdown(
            dispatch_fee=round(dispatch, 2),
            factoring_fee=round(factoring, 2),
            total_fees=round(dispatch + factoring, 2),
        )

    def score_load(
        self,
        breakdown: ProfitBreakdown,
        destination_market_score: Optional[float] = None,
    ) -> float:
        net_profit_norm = _normalize(breakdown.net_profit, -500, 2500)
        ppm = breakdown.net_profit / breakdown.loaded_miles if breakdown.loaded_miles > 0 else 0
        ppm_norm = _normalize(ppm, -0.5, 3.0)
        market_norm = destination_market_score if destination_market_score is not None else 50.0

        hours = max(breakdown.total_miles / 55.0, 1.0)
        profit_per_hour = breakdown.net_profit / hours
        time_norm = _normalize(profit_per_hour, 0, 80)

        return round(
            net_profit_norm * 0.40
            + ppm_norm * 0.30
            + market_norm * 0.20
            + time_norm * 0.10,
            2,
        )

    def calculate(
        self,
        load: LoadRecord,
        driver_lat: float,
        driver_lng: float,
        fuel_price_override: Optional[float] = None,
        destination_market_score: Optional[float] = None,
        deadhead_from_delivery: Optional[float] = None,
    ) -> ProfitBreakdown:
        fuel_price = fuel_price_override or self.settings.fuel_price_per_gallon

        pickup_lat = load.origin_lat or driver_lat
        pickup_lng = load.origin_lng or driver_lng
        dest_lat = load.dest_lat or pickup_lat
        dest_lng = load.dest_lng or pickup_lng

        deadhead_to = self.calculate_deadhead_to_pickup(
            driver_lat, driver_lng, pickup_lat, pickup_lng, load.equipment, fuel_price
        )
        deadhead_from = deadhead_from_delivery
        if deadhead_from is None:
            deadhead_from = self.estimate_deadhead_from_delivery(
                load.dest_city,
                load.dest_state,
                dest_lat,
                dest_lng,
                load.equipment,
                destination_market_score,
            )

        loaded_miles = load.miles
        total_miles = loaded_miles + deadhead_to.miles + deadhead_from

        fuel_breakdown = self.calculate_fuel_cost(
            loaded_miles, deadhead_to.miles, deadhead_from, load.equipment, fuel_price
        )

        driver_cost = self.calculate_driver_cost(total_miles, load.requirements)
        maint_mod = c.EQUIPMENT_MAINTENANCE_MODIFIER.get(load.equipment, 1.0)
        insurance_cost = round(total_miles * self.settings.insurance_per_mile, 2)
        maintenance_cost = round(total_miles * self.settings.maintenance_per_mile * maint_mod, 2)
        tolls_cost = round(total_miles * self.settings.tolls_per_mile, 2)
        overhead_cost = round(total_miles * self.settings.overhead_per_mile, 2)

        gross_rate = load.rate
        if load.requirements and load.requirements.lower() == "hazmat":
            gross_rate *= 1 + self.settings.hazmat_premium

        fees = self.calculate_fees(gross_rate)
        revenue = gross_rate

        total_costs = (
            fuel_breakdown.total_fuel
            + driver_cost
            + insurance_cost
            + maintenance_cost
            + tolls_cost
            + fees.total_fees
            + overhead_cost
        )
        net_profit = revenue - total_costs

        market_label = c.market_label_for_score(destination_market_score or 50.0)

        breakdown = ProfitBreakdown(
            load_id=load.load_id,
            gross_rate=round(gross_rate, 2),
            revenue=round(revenue, 2),
            loaded_miles=loaded_miles,
            deadhead_to_pickup=deadhead_to.miles,
            deadhead_from_delivery=deadhead_from,
            total_miles=round(total_miles, 1),
            fuel_cost=fuel_breakdown.total_fuel,
            fuel_breakdown=fuel_breakdown,
            driver_cost=driver_cost,
            insurance_cost=insurance_cost,
            maintenance_cost=maintenance_cost,
            tolls_cost=tolls_cost,
            dispatch_fee=fees.dispatch_fee,
            factoring_fee=fees.factoring_fee,
            overhead_cost=overhead_cost,
            total_costs=round(total_costs, 2),
            net_profit=round(net_profit, 2),
            profit_margin_percent=round((net_profit / revenue) * 100, 2) if revenue else 0.0,
            net_rate_per_mile=round(net_profit / loaded_miles, 2) if loaded_miles else 0.0,
            cost_per_mile=round(total_costs / total_miles, 2) if total_miles else 0.0,
            composite_score=0.0,
            destination_market_score=destination_market_score,
            destination_market_label=market_label,
            equipment=load.equipment,
            commodity=load.commodity,
            origin=f"{load.origin_city}, {load.origin_state}",
            destination=f"{load.dest_city}, {load.dest_state}",
            pickup_window=_format_window(load.pickup_start, load.pickup_end),
            delivery_window=_format_window(load.delivery_start, load.delivery_end),
            requirements=load.requirements,
        )
        breakdown.composite_score = self.score_load(breakdown, destination_market_score)
        return breakdown
