"""Request/response schemas for API Gateway."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RecommendRequest(BaseModel):
    message: str
    driver_id: Optional[str] = None
    session_id: Optional[str] = None
    driver_lat: Optional[float] = None
    driver_lng: Optional[float] = None
    equipment: Optional[str] = None
    max_deadhead: int = Field(default=250, ge=0, le=500)


class RatePredictRequest(BaseModel):
    origin_city: str
    origin_state: str
    dest_city: str
    dest_state: str
    equipment: str = "Dry Van"


class WhatIfRequest(BaseModel):
    lat: float
    lng: float
    equipment: Optional[str] = None
    fuel_price_override: Optional[float] = None


class CompareRequest(BaseModel):
    load_ids: list[str] = Field(..., min_length=2, max_length=3)
    driver_lat: float
    driver_lng: float


class ChainRequest(BaseModel):
    start_lat: float
    start_lng: float
    equipment: str = "Dry Van"
    num_hops: int = Field(default=3, ge=2, le=5)
    days: int = Field(default=5, ge=1, le=14)
    prefer_return_to_start: bool = True
    driver_id: Optional[str] = None
