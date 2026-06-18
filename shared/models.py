from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class LoadRecord(BaseModel):
    load_id: str
    origin_city: str
    origin_state: str
    origin_zip: Optional[str] = None
    origin_lat: Optional[float] = None
    origin_lng: Optional[float] = None
    dest_city: str
    dest_state: str
    dest_zip: Optional[str] = None
    dest_lat: Optional[float] = None
    dest_lng: Optional[float] = None
    pickup_start: Optional[datetime] = None
    pickup_end: Optional[datetime] = None
    delivery_start: Optional[datetime] = None
    delivery_end: Optional[datetime] = None
    equipment: str
    commodity: str
    weight_lbs: int
    miles: int
    rate: float
    rate_per_mile: float
    requirements: Optional[str] = None
    source: str = "text"
    format_type: Optional[str] = Field(default=None, description="verbose, reference, compact, or pdf")


class MarketScore(BaseModel):
    city: str
    state: str
    lat: float
    lng: float
    outbound_load_count: int
    inbound_load_count: int = 0
    avg_outbound_rate: float
    avg_inbound_rate: float
    lane_balance_ratio: float
    market_score: float
    equipment_diversity: int = 0
    label: str = "Unknown"


class DeadheadInfo(BaseModel):
    miles: float
    fuel_cost: float
    driver_cost: float
    total_cost: float


class FuelBreakdown(BaseModel):
    loaded_fuel: float
    deadhead_to_fuel: float
    deadhead_from_fuel: float
    total_fuel: float


class FeesBreakdown(BaseModel):
    dispatch_fee: float
    factoring_fee: float
    total_fees: float


class ProfitBreakdown(BaseModel):
    load_id: str
    gross_rate: float
    revenue: float
    loaded_miles: int
    deadhead_to_pickup: float
    deadhead_from_delivery: float
    total_miles: float
    fuel_cost: float
    fuel_breakdown: FuelBreakdown
    driver_cost: float
    insurance_cost: float
    maintenance_cost: float
    tolls_cost: float
    dispatch_fee: float
    factoring_fee: float
    overhead_cost: float
    total_costs: float
    net_profit: float
    profit_margin_percent: float
    net_rate_per_mile: float
    cost_per_mile: float
    composite_score: float
    destination_market_score: Optional[float] = None
    destination_market_label: str = "Unknown"
    equipment: str
    commodity: str
    origin: str
    destination: str
    pickup_window: Optional[str] = None
    delivery_window: Optional[str] = None
    requirements: Optional[str] = None


class RatePrediction(BaseModel):
    origin: str
    destination: str
    equipment: str
    current_avg_rate: float
    predicted_rate: float
    confidence_low: float
    confidence_high: float
    trend: str
    trend_percent: float


class MarketCluster(BaseModel):
    city: str
    state: str
    lat: float
    lng: float
    cluster_id: int
    cluster_label: str
    features: dict[str, Any]
