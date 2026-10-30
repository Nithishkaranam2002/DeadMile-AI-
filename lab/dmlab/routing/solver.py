"""One interface for every route solver.

A solver returns routes only. Anything it says about its own solution goes in
``solver_reported`` for information and is never used for metrics; the
feasibility checker and metrics recompute everything from the routes.
"""

import time
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from dmlab.routing.model import ProblemInstance


class SolveResult(BaseModel):
    solver: str
    routes: list[list[int]]
    found_solution: bool
    status: str
    runtime_s: float
    config: dict[str, Any]
    seed: int
    seed_used: bool  # False when the solver has no seed parameter
    solver_reported: dict[str, Any] = Field(default_factory=dict)


class Solver(ABC):
    name: str
    uses_seed: bool = True

    def __init__(self, **params: Any) -> None:
        self.params = params

    def config(self, time_limit_s: float) -> dict[str, Any]:
        return {"time_limit_s": time_limit_s, **self.params}

    def solve(self, inst: ProblemInstance, time_limit_s: float, seed: int) -> SolveResult:
        start = time.perf_counter()
        routes, found, status, reported = self._solve(inst, time_limit_s, seed)
        runtime = time.perf_counter() - start
        return SolveResult(
            solver=self.name,
            routes=[list(map(int, r)) for r in routes if r],
            found_solution=found,
            status=status,
            runtime_s=runtime,
            config=self.config(time_limit_s),
            seed=seed,
            seed_used=self.uses_seed,
            solver_reported=reported,
        )

    @abstractmethod
    def _solve(
        self, inst: ProblemInstance, time_limit_s: float, seed: int
    ) -> tuple[list[list[int]], bool, str, dict[str, Any]]:
        """Return (routes, found_solution, status, solver_reported)."""


def get_solver(name: str, **params: Any) -> Solver:
    # Imported here so a worker only loads the library it needs.
    if name == "pyvrp":
        from dmlab.routing.pyvrp_solver import PyVRPSolver

        return PyVRPSolver(**params)
    if name == "ortools":
        from dmlab.routing.ortools_solver import ORToolsSolver

        return ORToolsSolver(**params)
    if name == "nn":
        from dmlab.routing.nearest_neighbor import NearestNeighborSolver

        return NearestNeighborSolver(**params)
    raise ValueError(f"unknown solver {name!r}; choose pyvrp, ortools or nn")


SOLVER_NAMES = ("pyvrp", "ortools", "nn")
