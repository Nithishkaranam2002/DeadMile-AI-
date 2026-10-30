"""Formulation variants: change how the solver sees a problem, never the problem.

``apply`` returns a modified copy of an instance that is handed to the solver.
The routes it returns are always checked and measured on the original,
unchanged instance with our own feasibility checker and metrics (see
``dmlab.routing.runner.run_task``), so a formulation can only win by finding
routes that are better on the real problem.

Every setting tightens the problem the solver sees (a buffer), so a route that
is feasible for the solver is also feasible on the original:

* tw_late_buffer_share: each stop's latest arrival moves earlier by this share
  of its window width (time window slack, kept as a buffer).
* max_route_duration_factor: the solver's shift limit is this share of the real one.
* fleet_size_delta: the solver gets this many fewer vehicles (0 or negative).
* capacity_reserve_share: this share of each truck's capacity is held back,
  for example for same day pickups.

Cluster first, route second is a code variant (plugin) and arrives in Module 4.
"""

import math

from pydantic import BaseModel, ConfigDict, Field

from dmlab.routing.model import ProblemInstance


class Formulation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tw_late_buffer_share: float = Field(default=0.0, ge=0.0, le=0.5)
    max_route_duration_factor: float = Field(default=1.0, ge=0.5, le=1.0)
    fleet_size_delta: int = Field(default=0, ge=-10, le=0)
    capacity_reserve_share: float = Field(default=0.0, ge=0.0, le=0.5)

    def is_identity(self) -> bool:
        return self == Formulation()


def apply(inst: ProblemInstance, f: Formulation) -> ProblemInstance:
    """The instance as the solver should see it. The original is not modified."""
    if f.is_identity():
        return inst
    stops = [
        s.model_copy(
            update={
                "tw_late": s.tw_late - math.floor(f.tw_late_buffer_share * (s.tw_late - s.tw_early))
            }
        )
        for s in inst.stops
    ]
    fleet = inst.fleet.model_copy(
        update={
            "num_vehicles": max(1, inst.fleet.num_vehicles + f.fleet_size_delta),
            "capacity": math.floor(inst.fleet.capacity * (1 - f.capacity_reserve_share)),
            "max_shift": math.floor(inst.fleet.max_shift * f.max_route_duration_factor),
        }
    )
    return inst.model_copy(
        update={
            "stops": stops,
            "fleet": fleet,
            "metadata": {**inst.metadata, "formulation": f.model_dump()},
        }
    )
