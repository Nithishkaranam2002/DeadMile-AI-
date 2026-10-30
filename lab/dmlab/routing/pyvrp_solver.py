"""PyVRP solver (champion baseline).

Written against pyvrp 0.14.1 (iterated local search). Model API checked in the
installed source: Model.add_location / add_depot / add_vehicle_type /
add_client / add_edge, Model.solve(stop, seed, display), Result.best.routes().
"""

from typing import Any

from pyvrp import Model
from pyvrp.stop import MaxRuntime

from dmlab.routing.model import ProblemInstance
from dmlab.routing.solver import Solver


class PyVRPSolver(Solver):
    name = "pyvrp"

    def __init__(self, **params: Any) -> None:
        # Search settings are not wired yet (parameter variants come with the
        # agent). Refuse them so a variant can never silently run as default.
        if params:
            raise ValueError(f"PyVRPSolver takes no parameters yet, got {sorted(params)}")
        super().__init__()

    def _solve(
        self, inst: ProblemInstance, time_limit_s: float, seed: int
    ) -> tuple[list[list[int]], bool, str, dict[str, Any]]:
        m = Model()
        locs = [m.add_location(inst.depot.x, inst.depot.y, name=inst.depot.id)]
        locs += [m.add_location(s.x, s.y, name=s.id) for s in inst.stops]
        m.add_depot(locs[0], tw_early=inst.depot.tw_early, tw_late=inst.depot.tw_late)
        m.add_vehicle_type(
            num_available=inst.fleet.num_vehicles,
            capacity=inst.fleet.capacity,
            tw_early=inst.depot.tw_early,
            tw_late=inst.depot.tw_late,
            shift_duration=inst.fleet.max_shift,
        )
        for loc, s in zip(locs[1:], inst.stops, strict=True):
            m.add_client(
                loc,
                delivery=s.delivery,
                pickup=s.pickup,
                service_duration=s.service,
                tw_early=s.tw_early,
                tw_late=s.tw_late,
                name=s.id,
            )
        dist, dur = inst.dist, inst.dur
        for i, a in enumerate(locs):
            for j, b in enumerate(locs):
                if i != j:
                    m.add_edge(a, b, distance=int(dist[i, j]), duration=int(dur[i, j]))

        res = m.solve(stop=MaxRuntime(time_limit_s), seed=seed, display=False)

        # Client index c maps to stop node c + 1 (locations were added depot first).
        routes = [[a.idx + 1 for a in route if a.is_client()] for route in res.best.routes()]
        feasible = res.is_feasible()
        reported = {
            "is_feasible": feasible,
            "cost": float(res.cost()),
            "distance": int(res.best.distance()),
            "num_iterations": int(res.num_iterations),
            "runtime": float(res.runtime),
        }
        return routes, True, "feasible" if feasible else "infeasible", reported
