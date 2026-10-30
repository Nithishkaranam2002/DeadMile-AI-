"""PyVRP solver (champion baseline).

Written against pyvrp 0.14.1 (iterated local search). Model API checked in the
installed source: Model.add_location / add_depot / add_vehicle_type /
add_client / add_edge, Model.solve(stop, seed, display, params),
Result.best.routes().

Search settings (parameter variants) come as sections that map one to one to
pyvrp.solve.SolveParams (checked in pyvrp 0.14.1):

  {"ils": {num_iters_no_improvement, history_length, exhaustive_on_best},
   "penalty": {solutions_between_updates, penalty_increase, penalty_decrease,
               target_feasible, feas_tolerance, min_penalty, max_penalty},
   "neighbourhood": {weight_wait_time, num_neighbours, symmetric_proximity},
   "perturbation": {min_perturbations, max_perturbations},
   "operators": [names from pyvrp.search.OPERATORS]}

Unknown sections or keys are refused, so a variant can never silently run as
the default. PyVRP's own checks (for example history_length > 0) still apply.
The stopping criterion is always the suite's time limit; it is not a setting.
"""

from typing import Any

import pyvrp.search
from pyvrp import Model
from pyvrp.IteratedLocalSearch import IteratedLocalSearchParams
from pyvrp.PenaltyManager import PenaltyParams
from pyvrp.search import OPERATORS, NeighbourhoodParams, PerturbationParams
from pyvrp.solve import SolveParams
from pyvrp.stop import MaxRuntime

from dmlab.routing.model import ProblemInstance
from dmlab.routing.solver import Solver


class PyVRPSolver(Solver):
    name = "pyvrp"

    def __init__(self, **params: Any) -> None:
        super().__init__(**params)
        self.solve_params = build_solve_params(params)

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

        res = m.solve(
            stop=MaxRuntime(time_limit_s), seed=seed, display=False, params=self.solve_params
        )

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


SECTION_KEYS: dict[str, frozenset[str]] = {
    "ils": frozenset({"num_iters_no_improvement", "history_length", "exhaustive_on_best"}),
    "penalty": frozenset(
        {
            "solutions_between_updates",
            "penalty_increase",
            "penalty_decrease",
            "target_feasible",
            "feas_tolerance",
            "min_penalty",
            "max_penalty",
        }
    ),
    "neighbourhood": frozenset({"weight_wait_time", "num_neighbours", "symmetric_proximity"}),
    "perturbation": frozenset({"min_perturbations", "max_perturbations"}),
}
OPERATOR_NAMES = tuple(op.__name__ for op in OPERATORS)


def build_solve_params(params: dict[str, Any]) -> SolveParams:
    """SolveParams from sectioned settings. Empty settings give PyVRP's defaults."""
    unknown = set(params) - set(SECTION_KEYS) - {"operators"}
    if unknown:
        raise ValueError(f"unknown PyVRP settings {sorted(unknown)}")
    for section, keys in SECTION_KEYS.items():
        given = params.get(section, {})
        if not isinstance(given, dict):
            raise ValueError(f"PyVRP setting {section!r} must be a mapping")
        bad = set(given) - keys
        if bad:
            raise ValueError(f"unknown PyVRP {section} settings {sorted(bad)}")
    operators = OPERATORS
    if "operators" in params:
        names = params["operators"]
        bad = [n for n in names if n not in OPERATOR_NAMES]
        if bad or not names or len(set(names)) != len(names):
            raise ValueError(f"operators must be distinct names from {OPERATOR_NAMES}")
        operators = [getattr(pyvrp.search, n) for n in names]
    return SolveParams(
        ils=IteratedLocalSearchParams(**params.get("ils", {})),
        penalty=PenaltyParams(**params.get("penalty", {})),
        neighbourhood=NeighbourhoodParams(**params.get("neighbourhood", {})),
        operators=operators,
        perturbation=PerturbationParams(**params.get("perturbation", {})),
    )
