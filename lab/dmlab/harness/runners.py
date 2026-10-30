"""Runners execute solve tasks and hand back outcomes.

A task is one (solver config, instance, seed, time limit). Every runner calls
Module 1's ``run_task`` (solve, then our feasibility checker and metrics), so
results do not depend on where a task ran. Runners do not log; the caller logs
outcomes to MLflow.

``LocalRunner`` uses a process pool on this machine. A ``TemporalRunner`` can
be added later with the same contract: ``SolveTask`` and ``TaskOutcome`` are
pydantic models that serialize to JSON, so a Temporal workflow can fan tasks
out as activities that call ``run_task`` and stream outcomes back.
"""

import hashlib
import json
from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import get_context
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from dmlab.routing.runner import InstanceRef, run_task
from dmlab.routing.solver import SOLVER_NAMES, get_solver


class SolverConfig(BaseModel):
    """What a registry 'model' is for routing: a solver and its parameters."""

    model_config = ConfigDict(frozen=True)

    solver: str
    params: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, _: Any) -> None:
        if self.solver not in SOLVER_NAMES:
            raise ValueError(f"unknown solver {self.solver!r}; choose from {SOLVER_NAMES}")

    @property
    def uses_seed(self) -> bool:
        return get_solver(self.solver, **self.params).uses_seed

    def key(self) -> str:
        body = json.dumps(self.model_dump(), sort_keys=True, default=str)
        return hashlib.sha256(body.encode()).hexdigest()[:12]

    def label(self) -> str:
        if not self.params:
            return f"{self.solver} (default config)"
        return f"{self.solver} {json.dumps(self.params, sort_keys=True)}"


class SolveTask(BaseModel):
    model_config = ConfigDict(frozen=True)

    group: str  # which evaluation this task belongs to, e.g. "champion"
    config: SolverConfig
    ref: InstanceRef
    seed: int
    time_limit_s: float


class TaskOutcome(BaseModel):
    task: SolveTask
    payload: dict[str, Any] | None = None  # run_task output
    error: str | None = None


class Runner(ABC):
    @abstractmethod
    def run(self, tasks: Sequence[SolveTask]) -> Iterator[TaskOutcome]:
        """Yield one outcome per task, in completion order. Crashes become
        outcomes with ``error`` set; they are never dropped."""


def _execute(task: SolveTask) -> dict[str, Any]:
    return run_task(task.config.solver, task.config.params, task.ref, task.time_limit_s, task.seed)


class LocalRunner(Runner):
    def __init__(self, workers: int = 1) -> None:
        if workers < 1:
            raise ValueError("workers must be at least 1")
        self.workers = workers

    def run(self, tasks: Sequence[SolveTask]) -> Iterator[TaskOutcome]:
        ctx = get_context("spawn")
        with ProcessPoolExecutor(max_workers=self.workers, mp_context=ctx) as pool:
            futures = {pool.submit(_execute, t): t for t in tasks}
            for fut in as_completed(futures):
                task = futures[fut]
                try:
                    yield TaskOutcome(task=task, payload=fut.result())
                except Exception as exc:  # a crash is reported, never hidden
                    yield TaskOutcome(task=task, error=repr(exc))
