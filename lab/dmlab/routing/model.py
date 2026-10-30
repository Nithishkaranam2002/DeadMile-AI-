"""Internal problem model shared by every loader, solver, checker and metric.

All quantities are integers in internal units. ``Units`` says how to turn them
back into display units (for example Solomon distance is stored as
floor(10 * euclidean), Amazon distance as meters), and carries the honesty
labels that must sit next to any number derived from the instance.

Node indexing used by matrices and routes: node 0 is the depot, node i >= 1 is
``stops[i - 1]``. A route is a list of stop node indices, depot excluded.
"""

from functools import cached_property
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

StopKind = Literal["delivery", "pickup"]
Source = Literal["solomon", "amazon", "synthetic", "fixture"]


class Units(BaseModel):
    model_config = ConfigDict(frozen=True)

    distance_unit: str  # display name, e.g. "Solomon unit (abstract)" or "km"
    distance_scale: float  # internal integers per display unit
    time_unit: str  # display name, e.g. "Solomon time unit (abstract)" or "hour"
    time_scale: float  # internal integers per display unit
    demand_unit: str
    # True when time is measured in real hours, so "stops per driver hour" applies.
    time_is_hours: bool
    distance_label: str  # honesty label shown next to distances
    time_label: str  # honesty label shown next to durations


class Depot(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    x: float
    y: float
    tw_early: int
    tw_late: int


class Stop(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    kind: StopKind
    x: float
    y: float
    delivery: int = Field(ge=0)  # loaded at the depot, dropped here
    pickup: int = Field(ge=0)  # loaded here, brought back to the depot
    service: int = Field(ge=0)
    tw_early: int
    tw_late: int

    @model_validator(mode="after")
    def _check(self) -> "Stop":
        if self.kind == "delivery" and self.pickup != 0:
            raise ValueError(f"delivery stop {self.id} has a pickup amount")
        if self.kind == "pickup" and self.delivery != 0:
            raise ValueError(f"pickup stop {self.id} has a delivery amount")
        if self.tw_early > self.tw_late:
            raise ValueError(f"stop {self.id} has an empty time window")
        return self


class Fleet(BaseModel):
    model_config = ConfigDict(frozen=True)

    num_vehicles: int = Field(ge=1)
    capacity: int = Field(ge=0)
    max_shift: int = Field(ge=0)  # max route duration, internal time units


class ProblemInstance(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    source: Source
    slice: str  # Solomon class (C1, R2, ...) or Amazon city
    depot: Depot
    stops: list[Stop]
    fleet: Fleet
    distance: list[list[int]]
    duration: list[list[int]]
    units: Units
    data_version: str  # sha256 of the raw input this instance was built from
    labels: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> "ProblemInstance":
        n = len(self.stops) + 1
        for name in ("distance", "duration"):
            m = getattr(self, name)
            if len(m) != n or any(len(row) != n for row in m):
                raise ValueError(f"{name} matrix must be {n}x{n}")
            if any(v < 0 for row in m for v in row):
                raise ValueError(f"{name} matrix has negative values")
            if any(m[i][i] != 0 for i in range(n)):
                raise ValueError(f"{name} matrix diagonal must be zero")
        ids = [s.id for s in self.stops]
        if len(set(ids)) != len(ids) or self.depot.id in ids:
            raise ValueError("stop ids must be unique and differ from the depot id")
        return self

    @property
    def num_stops(self) -> int:
        return len(self.stops)

    @cached_property
    def dist(self) -> np.ndarray:
        return np.asarray(self.distance, dtype=np.int64)

    @cached_property
    def dur(self) -> np.ndarray:
        return np.asarray(self.duration, dtype=np.int64)

    def stop(self, node: int) -> Stop:
        """Stop at node index ``node`` (1 based)."""
        if node < 1 or node > len(self.stops):
            raise IndexError(f"node {node} is not a stop")
        return self.stops[node - 1]
