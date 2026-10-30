"""Routing metrics, computed from the final routes by our own code.

Everything comes from the instance and the feasibility checker's replay of the
routes; nothing comes from solver internals. Values are in display units
(instance.units). Cost per stop is only computed when every cost assumption in
configs/business.yaml is set; otherwise it is reported as not computed.
"""

import math
from typing import Any

from pydantic import BaseModel

from dmlab.routing.feasibility import FeasibilityReport
from dmlab.routing.model import ProblemInstance


class RouteMetrics(BaseModel):
    feasible: bool
    num_stops: int
    vehicles_used: int
    total_distance: float  # display distance units
    distance_per_stop: float
    total_duration: float  # display time units, travel + waiting + service
    # Stops per driver hour when time is in real hours; otherwise stops per 100
    # abstract time units (Solomon). The key name says which.
    productivity_name: str
    productivity: float
    time_window_violations: int
    total_lateness: float  # display time units
    runtime_s: float
    gap_to_bks_pct: float | None = None
    bks_distance: float | None = None
    total_distance_exact_euclidean: float | None = None  # Solomon only, information
    cost_per_stop: float | None = None
    cost_note: str


def exact_euclidean_distance(inst: ProblemInstance, routes: list[list[int]]) -> float:
    pts = [(inst.depot.x, inst.depot.y)] + [(s.x, s.y) for s in inst.stops]
    total = 0.0
    for r in routes:
        path = [0, *r, 0]
        for a, b in zip(path, path[1:], strict=False):
            total += math.dist(pts[a], pts[b])
    return total


def cost_per_stop(
    driver_hours: float, distance: float, stops: int, business: dict[str, Any], dist_key: str
) -> tuple[float | None, str]:
    rate_hour = business.get("cost_per_driver_hour")
    rate_dist = (business.get("cost_per_distance_unit") or {}).get(dist_key)
    if rate_hour is None or rate_dist is None:
        return None, "not computed: cost assumptions not set in configs/business.yaml"
    if stops == 0:
        return None, "not computed: no stops"
    value = (driver_hours * rate_hour + distance * rate_dist) / stops
    return value, "assumption: cost rates from configs/business.yaml"


def compute(
    inst: ProblemInstance,
    routes: list[list[int]],
    report: FeasibilityReport,
    runtime_s: float,
    bks_distance_internal: int | None = None,
    business: dict[str, Any] | None = None,
) -> RouteMetrics:
    u = inst.units
    stops = sum(len(r.nodes) for r in report.routes)
    dist_internal = sum(r.distance for r in report.routes)
    dur_internal = sum(r.duration for r in report.routes)
    total_distance = dist_internal / u.distance_scale
    total_duration = dur_internal / u.time_scale

    if u.time_is_hours:
        prod_name = "stops_per_driver_hour"
        prod = stops / total_duration if total_duration else 0.0
    else:
        prod_name = "stops_per_100_time_units"
        prod = 100 * stops / total_duration if total_duration else 0.0

    # A gap is only meaningful for a feasible solution of the same objective.
    gap = bks = None
    if bks_distance_internal and report.feasible:
        bks = bks_distance_internal / u.distance_scale
        gap = 100.0 * (dist_internal - bks_distance_internal) / bks_distance_internal

    exact = exact_euclidean_distance(inst, routes) if inst.source == "solomon" else None

    dist_key = "solomon_unit" if inst.source == "solomon" else "km"
    cps, note = None, "not computed: time is not in hours"
    if u.time_is_hours:
        cps, note = cost_per_stop(total_duration, total_distance, stops, business or {}, dist_key)

    return RouteMetrics(
        feasible=report.feasible,
        num_stops=stops,
        vehicles_used=len(report.routes),
        total_distance=total_distance,
        distance_per_stop=total_distance / stops if stops else 0.0,
        total_duration=total_duration,
        productivity_name=prod_name,
        productivity=prod,
        time_window_violations=report.time_window_violations,
        total_lateness=report.total_lateness / u.time_scale,
        runtime_s=runtime_s,
        gap_to_bks_pct=gap,
        bks_distance=bks,
        total_distance_exact_euclidean=exact,
        cost_per_stop=cps,
        cost_note=note,
    )
