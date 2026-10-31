"""Runners execute solve tasks and hand back outcomes.

A task is one (solver config, instance, seed, time limit). Every runner calls
Module 1's ``run_task`` (solve, then our feasibility checker and metrics), so
results do not depend on where a task ran. Runners do not log; the caller logs
outcomes to MLflow.

``LocalRunner`` uses a process pool on this machine. A ``TemporalRunner`` can
be added later with the same contract: ``SolveTask`` and ``TaskOutcome`` are
pydantic models that serialize to JSON, so a Temporal workflow can fan tasks
out as activities that call ``run_task`` and stream outcomes back.

Kill switch (Module 4): every runner checks it before it starts each task, so
no new solve run starts once it is on. Tasks are handed to the pool one at a
time (at most one waiting per worker), so nothing is queued past a check.

Plugin code (code variants) never runs on the host: ``LocalRunner`` refuses
any task whose config carries plugins. Those run in the sandbox runner
(dmlab/safeguards/sandbox), and so does the champion side of the same
comparison, so both sides run on the same machine (see ``execution_for``).
"""

import hashlib
import json
import signal
from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from multiprocessing import get_context
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from dmlab.paths import budgets_config
from dmlab.routing.formulation import Formulation
from dmlab.routing.runner import InstanceRef, run_task
from dmlab.routing.solver import SOLVER_NAMES, get_solver
from dmlab.safeguards import killswitch


class SolverConfig(BaseModel):
    """What a registry 'model' is for routing: a solver, its parameters and any
    plugin code. The plugin source text is part of the config, so it is part of
    ``key()`` and of the solver fingerprint: a changed plugin is never reused."""

    model_config = ConfigDict(frozen=True)

    solver: str
    params: dict[str, Any] = Field(default_factory=dict)
    # Plugin name -> Python source (code variants). Runs only in the sandbox.
    plugins: dict[str, str] = Field(default_factory=dict)
    # How the solver sees the problem (formulation variants, see
    # dmlab/routing/formulation.py). Results are always measured on the
    # original instance. Empty means the problem as given.
    formulation: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, _: Any) -> None:
        if self.solver not in SOLVER_NAMES:
            raise ValueError(f"unknown solver {self.solver!r}; choose from {SOLVER_NAMES}")
        if "time_limit_s" in self.params:
            raise ValueError("the time limit is fixed by the suite, not by a solver config")
        Formulation(**self.formulation)  # validate early

    @property
    def uses_seed(self) -> bool:
        return get_solver(self.solver, **self.params).uses_seed

    def key(self) -> str:
        dump = self.model_dump()
        if not dump["formulation"]:
            dump.pop("formulation")  # keeps keys of configs without one unchanged
        body = json.dumps(dump, sort_keys=True, default=str)
        return hashlib.sha256(body.encode()).hexdigest()[:12]

    def label(self) -> str:
        text = (
            f"{self.solver} {json.dumps(self.params, sort_keys=True)}"
            if self.params
            else f"{self.solver} (default config)"
        )
        if self.formulation:
            text += f" + formulation {json.dumps(self.formulation, sort_keys=True)}"
        for name, code in sorted(self.plugins.items()):
            text += f" + plugin {name} ({hashlib.sha256(code.encode()).hexdigest()[:8]})"
        return text


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


HOST = "host"
SANDBOX = "sandbox"


def execution_for(configs: Sequence[SolverConfig]) -> str:
    """Where a comparison runs: in the sandbox when any side carries plugin
    code, so champion and challenger always run on the same machine."""
    return SANDBOX if any(c.plugins for c in configs) else HOST


class Runner(ABC):
    execution: str = HOST
    workers: int = 1

    @abstractmethod
    def run(self, tasks: Sequence[SolveTask]) -> Iterator[TaskOutcome]:
        """Yield one outcome per task, in completion order. Crashes become
        outcomes with ``error`` set; they are never dropped. Raises
        ``KillSwitchActive`` when the kill switch is on before a task starts."""


WALL_CLOCK_ERROR = "wall clock budget exceeded"


class WallClockExceeded(Exception):
    pass


def wall_clock_limit() -> float | None:
    """Per run wall clock budget (configs/budgets.yaml per_run.wall_clock_seconds)."""
    value = (budgets_config().get("per_run") or {}).get("wall_clock_seconds")
    return float(value) if value else None


def _on_alarm(signum: int, frame: Any) -> None:
    raise WallClockExceeded()


def _execute(task: SolveTask) -> dict[str, Any]:
    """Run one task in a worker, under the per run wall clock budget.

    The budget is enforced with a real time interval timer in the worker's main
    thread. PyVRP's search loop and our own code run Python between steps, so
    the timer fires on time; OR Tools stops at its own time limit first.
    """
    limit = wall_clock_limit()
    if limit is not None:
        signal.signal(signal.SIGALRM, _on_alarm)
        signal.setitimer(signal.ITIMER_REAL, limit)
    try:
        c = task.config
        return run_task(c.solver, c.params, task.ref, task.time_limit_s, task.seed, c.formulation)
    except WallClockExceeded:
        raise RuntimeError(f"{WALL_CLOCK_ERROR}: run took longer than {limit:g} s") from None
    finally:
        if limit is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)


class LocalRunner(Runner):
    def __init__(self, workers: int = 1) -> None:
        if workers < 1:
            raise ValueError("workers must be at least 1")
        self.workers = workers

    def run(self, tasks: Sequence[SolveTask]) -> Iterator[TaskOutcome]:
        with_plugins = [t for t in tasks if t.config.plugins]
        if with_plugins:
            raise ValueError(
                "plugin code runs only in the sandbox, never on the host "
                f"({len(with_plugins)} tasks carry plugins)"
            )
        if not tasks:
            return
        ctx = get_context("spawn")
        todo = list(tasks)
        running: dict[Future, SolveTask] = {}
        pool = ProcessPoolExecutor(max_workers=self.workers, mp_context=ctx)
        try:
            while todo or running:
                while todo and len(running) < self.workers:
                    killswitch.check("before a solve run")
                    task = todo.pop(0)
                    running[pool.submit(_execute, task)] = task
                done, _ = wait(running, return_when=FIRST_COMPLETED)
                for fut in done:
                    task = running.pop(fut)
                    try:
                        yield TaskOutcome(task=task, payload=fut.result())
                    except Exception as exc:  # a crash is reported, never hidden
                        yield TaskOutcome(task=task, error=repr(exc))
        finally:
            # On a kill switch stop (or any error) nothing new starts; solves
            # already running finish within their time limit.
            pool.shutdown(wait=True, cancel_futures=True)
