"""Nearest neighbor heuristic (naive baseline), written by us.

From the current position, go to the nearest unvisited stop (by distance) that
can still be served: its load fits at every point of the route, service starts
inside its window, and the vehicle can still get back to the depot in time and
within the shift. If no stop fits, the vehicle returns and the next one starts.
If the fleet runs out, the remaining stops stay unvisited and the result is
reported as infeasible. Deterministic, so the seed is unused.

The shift check uses departure at the depot's earliest time, which is
conservative: the checker may find a shorter duration by departing later.
"""

from typing import Any

from dmlab.routing.model import ProblemInstance
from dmlab.routing.solver import Solver


class NearestNeighborSolver(Solver):
    name = "nn"
    uses_seed = False

    def _solve(
        self, inst: ProblemInstance, time_limit_s: float, seed: int
    ) -> tuple[list[list[int]], bool, str, dict[str, Any]]:
        dist = inst.dist.tolist()
        dur = inst.dur.tolist()
        cap = inst.fleet.capacity
        depart = inst.depot.tw_early
        unvisited = set(range(1, inst.num_stops + 1))
        routes: list[list[int]] = []

        while unvisited and len(routes) < inst.fleet.num_vehicles:
            route: list[int] = []
            cur, t = 0, depart
            max_load = final_load = 0  # deliveries on board at start count in max_load
            while True:
                best, best_d, best_state = None, None, None
                for j in unvisited:
                    s = inst.stop(j)
                    new_max = max(max_load + s.delivery, final_load + s.pickup)
                    if new_max > cap:
                        continue
                    start = max(t + dur[cur][j], s.tw_early)
                    if start > s.tw_late:
                        continue
                    back = start + s.service + dur[j][0]
                    if back > inst.depot.tw_late or back - depart > inst.fleet.max_shift:
                        continue
                    d = dist[cur][j]
                    if best_d is None or d < best_d or (d == best_d and j < best):
                        best, best_d = j, d
                        best_state = (start + s.service, new_max, final_load + s.pickup)
                if best is None:
                    break
                route.append(best)
                unvisited.remove(best)
                cur = best
                t, max_load, final_load = best_state
            if not route:
                break  # some stop cannot be served even by an empty vehicle
            routes.append(route)

        complete = not unvisited
        status = "complete" if complete else f"incomplete: {len(unvisited)} stops unvisited"
        return routes, complete, status, {"unvisited": len(unvisited)}
