"""Evaluate solver configs on a suite and log everything to MLflow.

Several evaluations of one comparison share one runner call, with their tasks
interleaved, so champion and candidate share the CPU cores evenly. Each
evaluation is a nested MLflow run (under the caller's active run) with one
nested solve run per (instance, seed), logged with Module 1's
``log_solve_run``.

Seed policy: seeded solvers run every seed of the suite. Solvers without a
seed (OR Tools, nearest neighbor) run once per instance, with the first seed
logged as unused.

Reuse: a spec with ``reuse=True`` (only ever the champion config) first looks
up matching earlier solve runs in MLflow by solver fingerprint (see reuse.py
and fingerprint.py) and runs only what is missing. Reused runs are marked on
every result and counted on the card. ``audit_reuse=K`` re-solves K of the
reused runs (seeded choice) and records how they compare, as a check that the
fingerprint misses nothing; audit runs never enter the statistics.
"""

import random
from collections import defaultdict
from pathlib import Path
from typing import Any

import mlflow
from pydantic import BaseModel

from dmlab.data.solomon import solomon_class
from dmlab.harness.fingerprint import fingerprint
from dmlab.harness.reuse import TAG_FINGERPRINT, TAG_INSTANCE, find_reusable, reuse_tags
from dmlab.harness.runners import Runner, SolverConfig, SolveTask
from dmlab.harness.splits import amazon_cities
from dmlab.harness.suites import Suite
from dmlab.routing.runner import load_instance, log_solve_run

EXPERIMENT = "harness"
MODULE = "2"


class EvalSpec(BaseModel):
    group: str  # e.g. "champion", "candidate"
    config: SolverConfig
    seeds: list[int]
    registry_ref: str | None = None  # e.g. "routing-solver v1 (@champion)"
    reuse: bool = False  # look up matching earlier runs in MLflow first
    audit_reuse: int = 0  # re-solve this many reused runs as a check


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
    # Information only metrics (never used for pass or fail).
    distance_per_stop: float | None = None
    productivity_name: str | None = None
    productivity: float | None = None
    time_window_violations: float | None = None
    cost_per_stop: float | None = None
    cost_note: str = ""
    reused: bool = False  # True when taken from an earlier MLflow run


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
    workers: int | None = None
    reused_runs: int = 0
    reused_run_ids: list[str] = []
    fingerprint: str = ""
    reuse_audit: list[dict[str, Any]] = []


def seeds_for(config: SolverConfig, seeds: list[int]) -> tuple[list[int], str]:
    if config.uses_seed:
        return list(seeds), f"seeded solver: ran {len(seeds)} seeds per instance {seeds}"
    return [seeds[0]], (
        "solver has no seed: ran once per instance (seed logged as unused); "
        "only seeded solvers get multiple seeds"
    )


def plan_tasks(
    specs: list[EvalSpec], suite: Suite, skip: set[tuple[str, str, int]] | None = None
) -> list[SolveTask]:
    """Tasks of all evaluations, interleaved by instance and seed. ``skip`` holds
    (group, instance, seed) keys that are reused instead of solved."""
    skip = skip or set()
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
                if (spec.group, _instance_name(ref.path, ref.kind), seed) not in skip
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
    workers = getattr(runner, "workers", None)
    fps = {s.group: fingerprint(s.config) for s in specs}
    reused = _lookup_reuse(specs, suite, git, workers, {g: fp for g, (fp, _) in fps.items()})
    skip = {(g, inst, seed) for g, found in reused.items() for (inst, seed) in found}
    tasks = plan_tasks(specs, suite, skip) + _audit_tasks(specs, suite, reused)
    outcomes = defaultdict(list)
    print(
        f"{len(tasks)} solve tasks ({len(skip)} reused from MLflow), "
        f"suite {suite.name}/{suite.split}, {suite.time_limit_s}s each"
    )
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
            TAG_FINGERPRINT: fps[spec.group][0],
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
            mlflow.log_dict(fps[spec.group][1], "fingerprint.json")
            extra = {
                "workers": workers,
                "time_limit_s": suite.time_limit_s,
                "fingerprint": fps[spec.group][0],
            }
            runs = [_instance_run(out, campaign, git, extra) for out in outcomes[spec.group]]
            reused_runs = {key: _from_mlflow(r) for key, r in reused.get(spec.group, {}).items()}
            runs += list(reused_runs.values())
            runs.sort(key=lambda r: (r.instance, r.seed))
            audit = []
            for out in outcomes[spec.group + AUDIT_SUFFIX]:
                fresh = _instance_run(out, campaign, git, extra | {"audit": True})
                old = reused_runs[(fresh.instance, fresh.seed)]
                diff = (
                    (fresh.total_distance - old.total_distance) / old.total_distance
                    if fresh.total_distance is not None and old.total_distance
                    else None
                )
                audit.append(
                    {
                        "instance": fresh.instance,
                        "seed": fresh.seed,
                        "reused_distance": old.total_distance,
                        "fresh_distance": fresh.total_distance,
                        "rel_diff": diff,
                        "reused_run_id": old.run_id,
                        "fresh_run_id": fresh.run_id,
                    }
                )
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
                workers=workers,
                reused_runs=sum(1 for r in runs if r.reused),
                reused_run_ids=[r.run_id for r in runs if r.reused and r.run_id],
                fingerprint=fps[spec.group][0],
                reuse_audit=audit,
            )
            mlflow.log_metrics(
                {
                    "runs": len(runs),
                    "errors": sum(1 for r in runs if r.error),
                    "feasible_runs": sum(1 for r in runs if r.feasible),
                    "reused_runs": ev.reused_runs,
                }
            )
            mlflow.log_dict(ev.model_dump(), "evaluation.json")
        evaluations.append(ev)
    return evaluations


AUDIT_SUFFIX = "__audit"


def _audit_tasks(
    specs: list[EvalSpec], suite: Suite, reused: dict[str, dict[tuple[str, int], Any]]
) -> list[SolveTask]:
    """Re-solve a seeded sample of reused runs, to check the fingerprint."""
    refs = {_instance_name(r.path, r.kind): r for r in suite.refs}
    tasks = []
    for spec in specs:
        keys = sorted(reused.get(spec.group, {}))
        k = min(spec.audit_reuse, len(keys))
        if k <= 0:
            continue
        rng = random.Random(f"audit:{suite.fingerprint()}:{spec.group}")
        for name, seed in sorted(rng.sample(keys, k)):
            tasks.append(
                SolveTask(
                    group=spec.group + AUDIT_SUFFIX,
                    config=spec.config,
                    ref=refs[name],
                    seed=seed,
                    time_limit_s=suite.time_limit_s,
                )
            )
    return tasks


def _lookup_reuse(
    specs: list[EvalSpec],
    suite: Suite,
    git: dict[str, Any],
    workers: int | None,
    fps: dict[str, str],
) -> dict[str, dict[tuple[str, int], Any]]:
    """group -> {(instance, seed): earlier MLflow run} for specs with reuse on."""
    wanted_specs = [s for s in specs if s.reuse]
    if not wanted_specs or workers is None or git["dirty"]:
        return {}
    exp = mlflow.get_experiment_by_name(EXPERIMENT)
    if exp is None:
        return {}
    versions = {
        _instance_name(ref.path, ref.kind): load_instance(ref).data_version for ref in suite.refs
    }
    out = {}
    for spec in wanted_specs:
        seeds, _ = seeds_for(spec.config, spec.seeds)
        wanted = {(name, s): v for name, v in versions.items() for s in seeds}
        out[spec.group] = find_reusable(
            exp.experiment_id, fps[spec.group], git, workers, suite.time_limit_s, wanted
        )
    return out


def _from_mlflow(run: Any) -> InstanceRun:
    """Rebuild a result from an earlier solve run (tags, params, metrics)."""
    tags, m = run.data.tags, run.data.metrics
    prod_name = next(
        (k for k in ("stops_per_driver_hour", "stops_per_100_time_units") if k in m), None
    )
    return InstanceRun(
        instance=tags[TAG_INSTANCE],
        slice=tags["slice"],
        source=tags["source"],
        seed=int(run.data.params["seed"]),
        seed_used=tags.get("seed_used_by_solver") == "true",
        feasible=m.get("feasible") == 1.0,
        total_distance=m.get("total_distance"),
        vehicles_used=int(m["vehicles_used"]) if "vehicles_used" in m else None,
        runtime_s=m.get("runtime_s"),
        distance_unit=tags.get("distance_unit", ""),
        distance_label=tags.get("distance_label", ""),
        labels=tags.get("labels", "").split(" | ") if tags.get("labels") else [],
        data_version=tags.get("data_version", ""),
        run_id=run.info.run_id,
        distance_per_stop=m.get("distance_per_stop"),
        productivity_name=prod_name,
        productivity=m.get(prod_name) if prod_name else None,
        time_window_violations=m.get("time_window_violations"),
        cost_per_stop=m.get("cost_per_stop"),
        cost_note=tags.get("cost_note", ""),
        reused=True,
    )


def _instance_run(
    out: Any, campaign: str, git: dict[str, Any], extra: dict[str, Any]
) -> InstanceRun:
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
    tags = {"group": t.group, TAG_FINGERPRINT: extra["fingerprint"]}
    if extra.get("audit"):
        tags["harness_audit"] = "true"
    if extra["workers"] is not None:
        tags |= reuse_tags(
            t.config, extra["fingerprint"], name, extra["workers"], extra["time_limit_s"]
        )
    run_id = log_solve_run(p, campaign, git, module=MODULE, extra_tags=tags)
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
        distance_per_stop=m["distance_per_stop"],
        productivity_name=m["productivity_name"],
        productivity=m["productivity"],
        time_window_violations=m["time_window_violations"],
        cost_per_stop=m["cost_per_stop"],
        cost_note=m["cost_note"],
    )
