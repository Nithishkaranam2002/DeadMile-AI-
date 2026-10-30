"""Evaluate solver configs on a suite and log everything to MLflow.

Several evaluations of one comparison share one runner call, with their tasks
interleaved, so champion and candidate share the CPU cores evenly. Each
evaluation is a nested MLflow run (under the caller's active run) with one
nested solve run per (instance, seed), logged with Module 1's
``log_solve_run``.

Seed policy: seeded solvers run every seed of the suite. Solvers without a
seed (OR Tools, nearest neighbor) run once per instance, with the first seed
logged as unused.
"""

from collections import defaultdict
from pathlib import Path
from typing import Any

import mlflow
from pydantic import BaseModel

from dmlab.data.solomon import solomon_class
from dmlab.harness.runners import Runner, SolverConfig, SolveTask
from dmlab.harness.splits import amazon_cities
from dmlab.harness.suites import Suite
from dmlab.routing.runner import log_solve_run

EXPERIMENT = "harness"
MODULE = "2"


class EvalSpec(BaseModel):
    group: str  # e.g. "champion", "candidate"
    config: SolverConfig
    seeds: list[int]
    registry_ref: str | None = None  # e.g. "routing-solver v1 (@champion)"


class InstanceRun(BaseModel):
    instance: str
    slice: str
    source: str
    seed: int
    seed_used: bool
    feasible: bool
    total_distance: float | None
    vehicles_used: int | None
    runtime_s: float | None
    distance_unit: str
    distance_label: str
    labels: list[str]
    data_version: str
    run_id: str | None
    error: str | None = None


class Evaluation(BaseModel):
    group: str
    config: SolverConfig
    registry_ref: str | None
    suite_name: str
    split: str
    suite_fingerprint: str
    time_limit_s: float
    seeds_run: list[int]
    seed_policy: str
    runs: list[InstanceRun]
    run_id: str


def seeds_for(config: SolverConfig, seeds: list[int]) -> tuple[list[int], str]:
    if config.uses_seed:
        return list(seeds), f"seeded solver: ran {len(seeds)} seeds per instance {seeds}"
    return [seeds[0]], (
        "solver has no seed: ran once per instance (seed logged as unused); "
        "only seeded solvers get multiple seeds"
    )


def plan_tasks(specs: list[EvalSpec], suite: Suite) -> list[SolveTask]:
    """Tasks of all evaluations, interleaved by instance and seed."""
    per_spec = []
    for spec in specs:
        seeds, _ = seeds_for(spec.config, spec.seeds)
        per_spec.append(
            [
                SolveTask(
                    group=spec.group,
                    config=spec.config,
                    ref=ref,
                    seed=seed,
                    time_limit_s=suite.time_limit_s,
                )
                for ref in suite.refs
                for seed in seeds
            ]
        )
    out: list[SolveTask] = []
    longest = max((len(t) for t in per_spec), default=0)
    for i in range(longest):
        out += [tasks[i] for tasks in per_spec if i < len(tasks)]
    return out


def _instance_name(ref_path: str, kind: str) -> str:
    """Name used for pairing: Solomon name (C101) or Amazon route id (RouteID_...)."""
    stem = Path(ref_path).stem
    return stem.upper() if kind == "solomon" else stem


def _slice_of(name: str, kind: str) -> str:
    if kind == "solomon":
        return solomon_class(name)
    if kind == "amazon":
        return next((c for c, ids in amazon_cities().items() if name in ids), "unknown")
    return "fixture"


def run_evaluations(
    specs: list[EvalSpec], suite: Suite, runner: Runner, campaign: str, git: dict[str, Any]
) -> list[Evaluation]:
    groups = [s.group for s in specs]
    if len(set(groups)) != len(groups):
        raise ValueError("evaluation groups must be unique")
    tasks = plan_tasks(specs, suite)
    outcomes = defaultdict(list)
    print(f"{len(tasks)} solve tasks, suite {suite.name}/{suite.split}, {suite.time_limit_s}s each")
    for i, out in enumerate(runner.run(tasks), start=1):
        outcomes[out.task.group].append(out)
        t = out.task
        name = _instance_name(t.ref.path, t.ref.kind)
        if out.error:
            print(f"[{i}/{len(tasks)}] {t.group:10s} {name[:14]:14s} s{t.seed}: ERROR {out.error}")
        else:
            m = out.payload["metrics"]
            print(
                f"[{i}/{len(tasks)}] {t.group:10s} {name[:14]:14s} s{t.seed:<2d} "
                f"feasible={m['feasible']!s:5s} dist={m['total_distance']:.1f} "
                f"t={m['runtime_s']:.1f}s"
            )

    evaluations = []
    for spec in specs:
        seeds, policy = seeds_for(spec.config, spec.seeds)
        tags = {
            "run_kind": "evaluation",
            "dmlab_module": MODULE,
            "campaign": campaign,
            "group": spec.group,
            "solver": spec.config.solver,
            "config_key": spec.config.key(),
            "suite": suite.name,
            "split": suite.split,
            "suite_fingerprint": suite.fingerprint(),
            "git_commit": git["commit"],
            "git_dirty": str(git["dirty"]).lower(),
            "seed_policy": policy,
        }
        if spec.registry_ref:
            tags["registry_ref"] = spec.registry_ref
        with mlflow.start_run(
            run_name=f"eval {spec.group} {spec.config.solver}", nested=True, tags=tags
        ) as run:
            mlflow.log_params(
                {
                    "solver": spec.config.solver,
                    "time_limit_s": suite.time_limit_s,
                    "seeds": ",".join(map(str, seeds)),
                    "num_instances": len(suite.refs),
                    **{f"solver.{k}": v for k, v in spec.config.params.items()},
                }
            )
            runs = []
            for out in sorted(outcomes[spec.group], key=lambda o: (o.task.ref.path, o.task.seed)):
                runs.append(_instance_run(out, campaign, git))
            ev = Evaluation(
                group=spec.group,
                config=spec.config,
                registry_ref=spec.registry_ref,
                suite_name=suite.name,
                split=suite.split,
                suite_fingerprint=suite.fingerprint(),
                time_limit_s=suite.time_limit_s,
                seeds_run=seeds,
                seed_policy=policy,
                runs=runs,
                run_id=run.info.run_id,
            )
            mlflow.log_metrics(
                {
                    "runs": len(runs),
                    "errors": sum(1 for r in runs if r.error),
                    "feasible_runs": sum(1 for r in runs if r.feasible),
                }
            )
            mlflow.log_dict(ev.model_dump(), "evaluation.json")
        evaluations.append(ev)
    return evaluations


def _instance_run(out: Any, campaign: str, git: dict[str, Any]) -> InstanceRun:
    t = out.task
    name = _instance_name(t.ref.path, t.ref.kind)
    if out.error:
        return InstanceRun(
            instance=name,
            slice=_slice_of(name, t.ref.kind),
            source=t.ref.kind,
            seed=t.seed,
            seed_used=t.config.uses_seed,
            feasible=False,
            total_distance=None,
            vehicles_used=None,
            runtime_s=None,
            distance_unit="",
            distance_label="",
            labels=[],
            data_version="",
            run_id=None,
            error=out.error,
        )
    p = out.payload
    run_id = log_solve_run(p, campaign, git, module=MODULE)
    inst, m = p["instance"], p["metrics"]
    return InstanceRun(
        instance=name,
        slice=inst["slice"],
        source=inst["source"],
        seed=t.seed,
        seed_used=p["result"]["seed_used"],
        feasible=m["feasible"],
        total_distance=m["total_distance"],
        vehicles_used=m["vehicles_used"],
        runtime_s=m["runtime_s"],
        distance_unit=inst["units"]["distance_unit"],
        distance_label=inst["units"]["distance_label"],
        labels=inst["labels"],
        data_version=inst["data_version"],
        run_id=run_id,
    )
