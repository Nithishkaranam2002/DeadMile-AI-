"""Independent feasibility checker.

Takes only the instance and the final routes (lists of stop node indices).
It never uses anything a solver reports about its own solution.

Rules, in internal units:
* Load: a vehicle leaves the depot carrying every delivery on its route.
  Deliveries are dropped and pickups are loaded along the way. The load must
  never exceed capacity, including at departure.
* Time: the vehicle leaves the depot at the depot's earliest time, waits if it
  arrives before a stop's window opens, and must start service no later than
  the window closes. It must be back at the depot by the depot's closing time.
* Shift length: route duration = return time - departure time, where the
  departure is pushed as late as possible without making any stop late or the
  return later (so needless waiting at the start is not counted). It must not
  exceed the fleet's max shift.
* Visits: every stop exactly once, no unknown nodes, no more routes than vehicles.
"""

from typing import Literal

from pydantic import BaseModel

from dmlab.routing.model import ProblemInstance

ViolationKind = Literal[
    "capacity",
    "time_window",
    "depot_return",
    "shift_length",
    "missing_stop",
    "duplicate_stop",
    "unknown_node",
    "too_many_routes",
]


class Violation(BaseModel):
    kind: ViolationKind
    route: int | None = None
    node: int | None = None
    amount: int = 0  # how far over the limit, in internal units


class RouteStats(BaseModel):
    nodes: list[int]
    distance: int
    departure: int  # latest departure that keeps the schedule (see module doc)
    end: int  # return time to the depot
    duration: int  # end - departure, includes travel, waiting and service
    service: int
    wait: int
    max_load: int


class FeasibilityReport(BaseModel):
    feasible: bool
    violations: list[Violation]
    counts: dict[str, int]
    time_window_violations: int
    total_lateness: int
    routes: list[RouteStats]


def _check_route(
    inst: ProblemInstance, r_idx: int, nodes: list[int], out: list[Violation]
) -> RouteStats:
    dist, dur = inst.dist, inst.dur
    cap = inst.fleet.capacity
    depot = inst.depot

    # Load profile.
    load = sum(inst.stop(n).delivery for n in nodes)
    max_load = load
    if load > cap:
        out.append(Violation(kind="capacity", route=r_idx, node=0, amount=load - cap))
    for n in nodes:
        s = inst.stop(n)
        load += s.pickup - s.delivery
        if load > cap:
            out.append(Violation(kind="capacity", route=r_idx, node=n, amount=load - cap))
        max_load = max(max_load, load)

    # Earliest schedule, tracking waits for the departure push.
    departure0 = depot.tw_early
    t = departure0
    prev = 0
    distance = 0
    service = 0
    cum_wait = 0
    late_found = False
    # Max push of the departure that keeps every stop on time: min over stops of
    # (tw_late - start + cumulative wait up to and including that stop).
    push_limit: int | None = None
    for n in nodes:
        s = inst.stop(n)
        distance += int(dist[prev, n])
        arrive = t + int(dur[prev, n])
        start = max(arrive, s.tw_early)
        cum_wait += start - arrive
        if start > s.tw_late:
            late_found = True
            out.append(Violation(kind="time_window", route=r_idx, node=n, amount=start - s.tw_late))
        else:
            room = s.tw_late - start + cum_wait
            push_limit = room if push_limit is None else min(push_limit, room)
        service += s.service
        t = start + s.service
        prev = n
    distance += int(dist[prev, 0])
    end = t + int(dur[prev, 0])
    if end > depot.tw_late:
        out.append(Violation(kind="depot_return", route=r_idx, amount=end - depot.tw_late))

    push = 0
    if not late_found:
        push = cum_wait if push_limit is None else min(cum_wait, push_limit)
        push = max(push, 0)
    departure = departure0 + push
    duration = end - departure
    if duration > inst.fleet.max_shift:
        out.append(
            Violation(kind="shift_length", route=r_idx, amount=duration - inst.fleet.max_shift)
        )

    return RouteStats(
        nodes=list(nodes),
        distance=distance,
        departure=departure,
        end=end,
        duration=duration,
        service=service,
        wait=cum_wait - push,
        max_load=max_load,
    )


def check(inst: ProblemInstance, routes: list[list[int]]) -> FeasibilityReport:
    violations: list[Violation] = []
    n = inst.num_stops
    seen: dict[int, int] = {}
    stats: list[RouteStats] = []

    non_empty = [r for r in routes if r]
    if len(non_empty) > inst.fleet.num_vehicles:
        violations.append(
            Violation(kind="too_many_routes", amount=len(non_empty) - inst.fleet.num_vehicles)
        )

    for r_idx, route in enumerate(non_empty):
        valid = []
        for node in route:
            if not isinstance(node, int) or node < 1 or node > n:
                violations.append(Violation(kind="unknown_node", route=r_idx, node=node))
                continue
            seen[node] = seen.get(node, 0) + 1
            valid.append(node)
        stats.append(_check_route(inst, r_idx, valid, violations))

    for node in range(1, n + 1):
        count = seen.get(node, 0)
        if count == 0:
            violations.append(Violation(kind="missing_stop", node=node))
        elif count > 1:
            violations.append(Violation(kind="duplicate_stop", node=node, amount=count - 1))

    counts: dict[str, int] = {}
    for v in violations:
        counts[v.kind] = counts.get(v.kind, 0) + 1
    tw = [v for v in violations if v.kind == "time_window"]
    return FeasibilityReport(
        feasible=not violations,
        violations=violations,
        counts=counts,
        time_window_violations=len(tw),
        total_lateness=sum(v.amount for v in tw),
        routes=stats,
    )
