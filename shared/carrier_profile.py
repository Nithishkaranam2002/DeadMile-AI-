"""Carrier cost profile model for per-fleet profitability."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CarrierCostProfile(BaseModel):
    carrier_id: str = "default"
    company_name: str = "My Fleet"
    default_equipment: str = "Dry Van"
    max_deadhead_miles: int = Field(default=250, ge=50, le=500)
    fuel_price_per_gallon: float = Field(default=3.90, ge=2.0, le=8.0)
    avg_mpg_loaded: float = Field(default=6.0, ge=4.0, le=12.0)
    avg_mpg_empty: float = Field(default=7.0, ge=4.0, le=14.0)
    driver_cpm: float = Field(default=0.55, ge=0.2, le=2.0)
    insurance_per_mile: float = Field(default=0.08, ge=0.0, le=0.5)
    maintenance_per_mile: float = Field(default=0.15, ge=0.0, le=0.5)
    tolls_per_mile: float = Field(default=0.04, ge=0.0, le=0.3)
    dispatch_fee_percent: float = Field(default=0.05, ge=0.0, le=0.2)
    factoring_fee_percent: float = Field(default=0.03, ge=0.0, le=0.1)
    overhead_per_mile: float = Field(default=0.05, ge=0.0, le=0.3)
    home_city: Optional[str] = None
    home_state: Optional[str] = None

    def to_cost_overrides(self) -> dict[str, float]:
        return {
            "fuel_price_per_gallon": self.fuel_price_per_gallon,
            "avg_mpg_loaded": self.avg_mpg_loaded,
            "avg_mpg_empty": self.avg_mpg_empty,
            "driver_cpm": self.driver_cpm,
            "insurance_per_mile": self.insurance_per_mile,
            "maintenance_per_mile": self.maintenance_per_mile,
            "tolls_per_mile": self.tolls_per_mile,
            "dispatch_fee_percent": self.dispatch_fee_percent,
            "factoring_fee_percent": self.factoring_fee_percent,
            "overhead_per_mile": self.overhead_per_mile,
        }


class CarrierCostProfileUpdate(BaseModel):
    company_name: Optional[str] = None
    default_equipment: Optional[str] = None
    max_deadhead_miles: Optional[int] = Field(default=None, ge=50, le=500)
    fuel_price_per_gallon: Optional[float] = Field(default=None, ge=2.0, le=8.0)
    avg_mpg_loaded: Optional[float] = Field(default=None, ge=4.0, le=12.0)
    avg_mpg_empty: Optional[float] = Field(default=None, ge=4.0, le=14.0)
    driver_cpm: Optional[float] = Field(default=None, ge=0.2, le=2.0)
    insurance_per_mile: Optional[float] = Field(default=None, ge=0.0, le=0.5)
    maintenance_per_mile: Optional[float] = Field(default=None, ge=0.0, le=0.5)
    tolls_per_mile: Optional[float] = Field(default=None, ge=0.0, le=0.3)
    dispatch_fee_percent: Optional[float] = Field(default=None, ge=0.0, le=0.2)
    factoring_fee_percent: Optional[float] = Field(default=None, ge=0.0, le=0.1)
    overhead_per_mile: Optional[float] = Field(default=None, ge=0.0, le=0.3)
    home_city: Optional[str] = None
    home_state: Optional[str] = None
