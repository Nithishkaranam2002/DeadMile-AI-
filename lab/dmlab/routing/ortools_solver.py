"""Google OR Tools routing solver (second baseline).

Written against ortools 9.15 (constraint_solver.pywrapcp, checked in the
installed source). OR Tools routing has no random seed parameter, so the seed
is logged but marked as unused.

Default first solution strategy is PARALLEL_CHEAPEST_INSERTION: with
PATH_CHEAPEST_ARC, OR Tools found no first solution at all for Solomon R101 and
R105 within 30 s (tight time windows). Chosen once, before any full run.

Load model:
* Delivery only instances: one capacity dimension counting deliveries.
* Instances with pickups: a "delivered" dimension counts deliveries along the
  route, and a "load" dimension with a free start value carries
  pickup - delivery per stop. The load at the start is tied to the route's
  total deliveries, so the load is exact at every point and capped by capacity.
"""

from typing import Any

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from dmlab.routing.model import ProblemInstance
from dmlab.routing.solver import Solver

FIRST_SOLUTION = routing_enums_pb2.FirstSolutionStrategy
METAHEURISTIC = routing_enums_pb2.LocalSearchMetaheuristic


class ORToolsSolver(Solver):
    name = "ortools"
    uses_seed = False

    def __init__(
        self,
        first_solution_strategy: str = "PARALLEL_CHEAPEST_INSERTION",
        local_search_metaheuristic: str = "GUIDED_LOCAL_SEARCH",
    ) -> None:
        super().__init__(
            first_solution_strategy=first_solution_strategy,
            local_search_metaheuristic=local_search_metaheuristic,
        )

    def _solve(
        self, inst: ProblemInstance, time_limit_s: float, seed: int
    ) -> tuple[list[list[int]], bool, str, dict[str, Any]]:
        n = inst.num_stops + 1
        k = inst.fleet.num_vehicles
        cap = inst.fleet.capacity
        manager = pywrapcp.RoutingIndexManager(n, k, 0)
        model = pywrapcp.RoutingModel(manager)

        dist = inst.dist.tolist()
        service = [0] + [s.service for s in inst.stops]
        travel = inst.dur.tolist()
        time_matrix = [[service[i] + travel[i][j] for j in range(n)] for i in range(n)]

        cost_cb = model.RegisterTransitMatrix(dist)
        model.SetArcCostEvaluatorOfAllVehicles(cost_cb)

        # Time: cumul = service start time; slack = waiting.
        horizon = inst.depot.tw_late
        time_cb = model.RegisterTransitMatrix(time_matrix)
        model.AddDimension(time_cb, horizon, horizon, False, "time")
        time_dim = model.GetDimensionOrDie("time")
        for node in range(1, n):
            s = inst.stop(node)
            time_dim.CumulVar(manager.NodeToIndex(node)).SetRange(s.tw_early, s.tw_late)
        for v in range(k):
            time_dim.CumulVar(model.Start(v)).SetRange(inst.depot.tw_early, inst.depot.tw_late)
            time_dim.CumulVar(model.End(v)).SetRange(inst.depot.tw_early, inst.depot.tw_late)
            time_dim.SetSpanUpperBoundForVehicle(inst.fleet.max_shift, v)
            model.AddVariableMaximizedByFinalizer(time_dim.CumulVar(model.Start(v)))
            model.AddVariableMinimizedByFinalizer(time_dim.CumulVar(model.End(v)))

        delivery = [0] + [s.delivery for s in inst.stops]
        pickup = [0] + [s.pickup for s in inst.stops]
        delivered_cb = model.RegisterUnaryTransitVector(delivery)
        model.AddDimension(delivered_cb, 0, cap, True, "delivered")
        if any(pickup):
            delivered_dim = model.GetDimensionOrDie("delivered")
            net_cb = model.RegisterUnaryTransitVector(
                [p - d for p, d in zip(pickup, delivery, strict=True)]
            )
            model.AddDimension(net_cb, 0, cap, False, "load")
            load_dim = model.GetDimensionOrDie("load")
            solver = model.solver()
            for v in range(k):
                solver.Add(
                    load_dim.CumulVar(model.Start(v)) == delivered_dim.CumulVar(model.End(v))
                )

        params = pywrapcp.DefaultRoutingSearchParameters()
        params.first_solution_strategy = getattr(
            FIRST_SOLUTION, self.params["first_solution_strategy"]
        )
        params.local_search_metaheuristic = getattr(
            METAHEURISTIC, self.params["local_search_metaheuristic"]
        )
        params.time_limit.FromMilliseconds(int(time_limit_s * 1000))

        assignment = model.SolveWithParameters(params)
        status = routing_enums_pb2.RoutingSearchStatus.Value.Name(model.status())
        if assignment is None:
            return [], False, status, {"status": status}

        routes: list[list[int]] = []
        for v in range(k):
            idx = assignment.Value(model.NextVar(model.Start(v)))
            route = []
            while not model.IsEnd(idx):
                route.append(manager.IndexToNode(idx))
                idx = assignment.Value(model.NextVar(idx))
            routes.append(route)
        reported = {"status": status, "objective": int(assignment.ObjectiveValue())}
        return routes, True, status, reported
