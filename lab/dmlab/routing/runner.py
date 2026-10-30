"""Run solvers on instances and log every run to MLflow.

Solving happens in worker processes (dmlab.harness.runners.LocalRunner). Each
worker loads the instance, solves, then runs our feasibility checker and
metrics on the returned routes. The
parent process does all MLflow logging: one parent run per batch, one child
run per (solver, instance, seed).
"""

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mlflow
import numpy as np
import yaml

from dmlab.data.amazon import load_amazon
from dmlab.data.bks import load_dimacs_bks
from dmlab.data.solomon import list_instances, load_solomon
from dmlab.paths import CONFIG_DIR, LAB_DIR, datasets_config, load_config
from dmlab.routing.feasibility import check
from dmlab.routing.formulation import Formulation
from dmlab.routing.formulation import apply as apply_formulation
from dmlab.routing.metrics import compute
from dmlab.routing.model import ProblemInstance
from dmlab.routing.solver import get_solver
from dmlab.tracking import configure_mlflow, git_info

EXPERIMENT = "routing-baselines"
BKS_CSV = LAB_DIR / "data/bks.csv"


@dataclass(frozen=True)
class InstanceRef:
    kind: str  # "solomon", "amazon" or "fixture"
    path: str


def resolve_instances(spec: str) -> list[InstanceRef]:
    """Parse specs like 'solomon:all', 'solomon:C101,R205', 'amazon:boston',
    'amazon:all', or 'file:<path to a Solomon format file>'. Comma separated
    groups can be joined with '+', e.g. 'solomon:all+amazon:all'."""
    cfg = datasets_config()
    refs: list[InstanceRef] = []
    for part in spec.split("+"):
        kind, _, what = part.partition(":")
        if kind == "solomon":
            raw = LAB_DIR / cfg["solomon"]["raw_dir"]
            paths = list_instances(raw)
            if what != "all":
                wanted = {w.strip().lower() for w in what.split(",")}
                paths = [p for p in paths if p.stem.lower() in wanted]
                missing = wanted - {p.stem.lower() for p in paths}
                if missing:
                    raise SystemExit(f"Solomon instances not found: {sorted(missing)}")
            refs += [InstanceRef("solomon", str(p)) for p in paths]
        elif kind == "amazon":
            subset_file = CONFIG_DIR / "amazon_subset.yaml"
            if not subset_file.exists():
                raise SystemExit("No Amazon subset yet: run `uv run dmlab-data fetch-amazon`")
            selected = yaml.safe_load(subset_file.read_text())["selected"]
            cities = list(selected) if what == "all" else [what.strip().capitalize()]
            processed = LAB_DIR / cfg["amazon"]["processed_dir"]
            for city in cities:
                if city not in selected:
                    raise SystemExit(f"unknown Amazon city {city!r}")
                refs += [
                    InstanceRef("amazon", str(processed / f"{r}.json")) for r in selected[city]
                ]
        elif kind == "file":
            refs.append(InstanceRef("fixture", what))
        else:
            raise SystemExit(f"cannot parse instance spec {part!r}")
    return refs


def load_instance(ref: InstanceRef) -> ProblemInstance:
    if ref.kind == "solomon":
        return load_solomon(Path(ref.path))
    if ref.kind == "fixture":
        return load_solomon(Path(ref.path), source="fixture")
    a = datasets_config()["amazon"]["assumptions"]
    return load_amazon(Path(ref.path), a["vans_per_route"], a["shift_hours"])


def run_task(
    solver_name: str,
    params: dict[str, Any],
    ref: InstanceRef,
    time_limit_s: float,
    seed: int,
    formulation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Solve, then check and measure on the original instance.

    With a formulation, the solver sees a modified copy (see formulation.py);
    the feasibility check and every metric still use the original instance.
    """
    random.seed(seed)
    np.random.seed(seed)
    inst = load_instance(ref)
    form = Formulation(**(formulation or {}))
    solver_view = apply_formulation(inst, form)
    result = get_solver(solver_name, **params).solve(solver_view, time_limit_s, seed)
    report = check(inst, result.routes)
    bks = load_dimacs_bks(BKS_CSV).get(inst.name) if inst.source == "solomon" else None
    metrics = compute(inst, result.routes, report, result.runtime_s, bks, load_config("business"))
    return {
        "instance": {
            "name": inst.name,
            "source": inst.source,
            "slice": inst.slice,
            "num_stops": inst.num_stops,
            "fleet": inst.fleet.model_dump(),
            "units": inst.units.model_dump(),
            "data_version": inst.data_version,
            "labels": inst.labels,
            "metadata": inst.metadata,
            "stop_ids": [s.id for s in inst.stops],
        },
        "result": result.model_dump(),
        "report": report.model_dump(),
        "metrics": metrics.model_dump(),
        "bks_used": bks is not None,
        "formulation": None if form.is_identity() else form.model_dump(),
    }


def log_solve_run(
    payload: dict[str, Any],
    campaign: str,
    git: dict[str, Any],
    module: str = "1",
    extra_tags: dict[str, str] | None = None,
) -> str:
    """Log one solve as an MLflow run, nested under the active run."""
    inst, res, rep, m = (payload[k] for k in ("instance", "result", "report", "metrics"))
    units = inst["units"]
    tags = {
        "run_kind": "solve",
        "dmlab_module": module,
        "campaign": campaign,
        "solver": res["solver"],
        "instance": inst["name"],
        "source": inst["source"],
        "slice": inst["slice"],
        "data_version": inst["data_version"],
        "git_commit": git["commit"],
        "git_dirty": str(git["dirty"]).lower(),
        "seed_used_by_solver": str(res["seed_used"]).lower(),
        "solver_status": res["status"],
        "distance_unit": units["distance_unit"],
        "distance_label": units["distance_label"],
        "time_label": units["time_label"],
        "labels": " | ".join(inst["labels"]),
        "cost_note": m["cost_note"],
    }
    tags.update(extra_tags or {})
    if payload.get("formulation"):
        tags["formulation"] = "solver saw a modified copy; checked on the original instance"
    if payload["bks_used"]:
        tags["bks_objective"] = "distance_only, dimacs_trunc1 (floor(10*d))"
    params = {
        "seed": res["seed"],
        "time_limit_s": res["config"]["time_limit_s"],
        "num_stops": inst["num_stops"],
        "fleet_vehicles": inst["fleet"]["num_vehicles"],
        "fleet_capacity": inst["fleet"]["capacity"],
        "fleet_max_shift": inst["fleet"]["max_shift"],
        "objective": "total distance",
        **{f"solver.{k}": v for k, v in res["config"].items() if k != "time_limit_s"},
        **{f"formulation.{k}": v for k, v in (payload.get("formulation") or {}).items()},
    }
    metrics = {
        "feasible": float(m["feasible"]),
        "found_solution": float(res["found_solution"]),
        "num_stops_routed": m["num_stops"],
        "vehicles_used": m["vehicles_used"],
        "total_distance": m["total_distance"],
        "distance_per_stop": m["distance_per_stop"],
        "total_duration": m["total_duration"],
        m["productivity_name"]: m["productivity"],
        "time_window_violations": m["time_window_violations"],
        "total_lateness": m["total_lateness"],
        "runtime_s": m["runtime_s"],
        "violations": len(rep["violations"]),
    }
    for key in (
        "gap_to_bks_pct",
        "bks_distance",
        "total_distance_exact_euclidean",
        "cost_per_stop",
    ):
        if m[key] is not None:
            metrics[key] = m[key]

    run_name = f"{res['solver']} {inst['name']} s{res['seed']}"
    with mlflow.start_run(run_name=run_name, nested=True, tags=tags) as run:
        mlflow.log_params(params)
        mlflow.log_metrics(metrics)
        ids = inst["stop_ids"]
        solution = {
            "routes_nodes": res["routes"],
            "routes_stop_ids": [
                [ids[n - 1] for n in r if 1 <= n <= len(ids)] for r in res["routes"]
            ],
            "solver_reported (information only)": res["solver_reported"],
        }
        mlflow.log_dict(solution, "solution.json")
        mlflow.log_dict(rep, "feasibility.json")
        mlflow.log_dict({k: v for k, v in inst.items() if k != "stop_ids"}, "instance.json")
        return run.info.run_id


def run_batch(
    solvers: list[str],
    refs: list[InstanceRef],
    time_limit_s: float,
    seed: int,
    workers: int,
    campaign: str,
    solver_params: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    uri = configure_mlflow()
    git = git_info().model_dump()
    mlflow.set_experiment(EXPERIMENT)
    solver_params = solver_params or {}
    # Interleave solvers so concurrent workers mix solvers, not one solver at a time.
    tasks = [(s, ref) for ref in refs for s in solvers]
    summaries: list[dict[str, Any]] = []
    parent_tags = {
        "run_kind": "batch",
        "dmlab_module": "1",
        "campaign": campaign,
        "git_commit": git["commit"],
        "git_dirty": str(git["dirty"]).lower(),
    }
    with mlflow.start_run(run_name=f"batch {campaign}", tags=parent_tags):
        mlflow.log_params(
            {
                "solvers": ",".join(solvers),
                "num_instances": len(refs),
                "time_limit_s": time_limit_s,
                "seed": seed,
                "workers": workers,
            }
        )
        if git["dirty"]:
            mlflow.log_text("\n".join(git["changed_files"]), "git_changed_files.txt")
        print(f"MLflow: {uri}, experiment {EXPERIMENT}, {len(tasks)} runs, {workers} workers")
        from dmlab.harness.runners import LocalRunner, SolverConfig, SolveTask

        solve_tasks = [
            SolveTask(
                group=s,
                config=SolverConfig(solver=s, params=solver_params.get(s, {})),
                ref=ref,
                seed=seed,
                time_limit_s=time_limit_s,
            )
            for s, ref in tasks
        ]
        for i, out in enumerate(LocalRunner(workers).run(solve_tasks), start=1):
            s, ref = out.task.config.solver, out.task.ref
            if out.error is not None:
                print(f"[{i}/{len(tasks)}] {s} {Path(ref.path).stem}: ERROR {out.error}")
                summaries.append({"solver": s, "instance": ref.path, "error": out.error})
                continue
            payload = out.payload
            log_solve_run(payload, campaign, git)
            m = payload["metrics"]
            gap = m["gap_to_bks_pct"]
            print(
                f"[{i}/{len(tasks)}] {s:8s} {payload['instance']['name'][:12]:12s} "
                f"feasible={m['feasible']!s:5s} dist={m['total_distance']:.1f} "
                f"veh={m['vehicles_used']} "
                + (f"gap={gap:.2f}% " if gap is not None else "")
                + f"t={m['runtime_s']:.1f}s"
            )
            summaries.append({"solver": s, "instance": payload["instance"]["name"], "metrics": m})
        errors = sum(1 for x in summaries if "error" in x)
        mlflow.log_metric("errors", errors)
        mlflow.log_text(json.dumps(summaries, indent=1, default=str), "batch_summary.json")
    return summaries
