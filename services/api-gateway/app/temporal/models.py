"""Temporal workflow data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ChainParams:
    start_lat: float
    start_lng: float
    equipment: str
    num_hops: int = 3
    days: int = 5
    prefer_return_to_start: bool = True
    driver_id: Optional[str] = None


@dataclass
class ChainResult:
    chains: list[dict[str, Any]] = field(default_factory=list)
    total_evaluated: int = 0
    workflow_id: Optional[str] = None
