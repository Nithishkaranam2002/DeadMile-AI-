"""MLflow model registry for solver configs, with aliases @champion and @challenger.

A registered "model" here is a solver config, not weights. Each version points
at the artifacts of a registry run holding ``solver_config.json`` (and, for
PyVRP, the effective defaults read from the installed library), plus a report
card when one exists. Stages are deprecated in MLflow; only aliases are used.

``bootstrap_champion`` sets @champion only when no champion exists yet. Moving
@champion afterwards is the promotion gate's job, with human approval
(Module 4), so this module has no general "set champion" call.
"""

import dataclasses
import importlib.metadata
from typing import Any

import mlflow
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException

from dmlab.harness.runners import SolverConfig
from dmlab.tracking import configure_mlflow, git_info

MODEL_NAME = "routing-solver"
REGISTRY_EXPERIMENT = "registry"
CHAMPION = "champion"
CHALLENGER = "challenger"
CONFIG_ARTIFACT = "solver_config.json"


def effective_defaults(config: SolverConfig) -> dict[str, Any]:
    """What the solver actually runs with, read from the installed library."""
    if config.solver == "pyvrp":
        from pyvrp.solve import SolveParams

        p = SolveParams()
        ils = dataclasses.asdict(p.ils)
        ils.pop("callbacks", None)
        n = p.neighbourhood
        return {
            "library": f"pyvrp {importlib.metadata.version('pyvrp')}",
            "algorithm": "iterated local search with late acceptance",
            "ils": ils,
            "penalty": dataclasses.asdict(p.penalty),
            "neighbourhood": {
                "weight_wait_time": n.weight_wait_time,
                "num_neighbours": n.num_neighbours,
                "symmetric_proximity": n.symmetric_proximity,
            },
            "perturbation": {
                "min_perturbations": p.perturbation.min_perturbations,
                "max_perturbations": p.perturbation.max_perturbations,
            },
            "operators": [op.__name__ for op in p.operators],
            "stop": "MaxRuntime(time limit of the suite)",
        }
    if config.solver == "ortools":
        from dmlab.routing.ortools_solver import ORToolsSolver

        return {
            "library": f"ortools {importlib.metadata.version('ortools')}",
            **ORToolsSolver(**config.params).params,
        }
    return {"library": "dmlab (our own code)", **config.params}


def _client() -> MlflowClient:
    configure_mlflow()
    return MlflowClient()


def register(
    config: SolverConfig, description: str, report_card: dict[str, Any] | None = None
) -> str:
    """Register a solver config as a new version of MODEL_NAME. Returns the version."""
    client = _client()
    mlflow.set_experiment(REGISTRY_EXPERIMENT)
    git = git_info()
    tags = {
        "run_kind": "registry",
        "solver": config.solver,
        "config_key": config.key(),
        "git_commit": git.commit,
        "git_dirty": str(git.dirty).lower(),
    }
    with mlflow.start_run(run_name=f"register {config.label()}", tags=tags) as run:
        mlflow.log_dict(
            {"config": config.model_dump(), "effective_defaults": effective_defaults(config)},
            CONFIG_ARTIFACT,
        )
        if report_card is not None:
            mlflow.log_dict(report_card, "report_card.json")
        source = run.info.artifact_uri
        run_id = run.info.run_id
    try:
        client.get_registered_model(MODEL_NAME)
    except MlflowException:
        client.create_registered_model(
            MODEL_NAME, description="Route solver configs (a 'model' is a solver config)."
        )
    mv = client.create_model_version(
        MODEL_NAME,
        source=source,
        run_id=run_id,
        tags={"solver": config.solver, "config_key": config.key()},
        description=description,
    )
    return str(mv.version)


def get_alias(alias: str) -> tuple[str, SolverConfig] | None:
    """(version, config) for an alias, or None when the alias is not set."""
    client = _client()
    try:
        mv = client.get_model_version_by_alias(MODEL_NAME, alias)
    except MlflowException:
        return None
    data = mlflow.artifacts.load_dict(f"{mv.source}/{CONFIG_ARTIFACT}")
    return str(mv.version), SolverConfig(**data["config"])


def bootstrap_champion(config: SolverConfig) -> str:
    """Register the first champion. Refuses when a champion already exists."""
    existing = get_alias(CHAMPION)
    if existing is not None:
        raise RuntimeError(
            f"@{CHAMPION} already exists (version {existing[0]}); moving it needs the "
            "promotion gate and human approval"
        )
    version = register(config, "First champion: default config (bootstrap, Module 2).")
    _client().set_registered_model_alias(MODEL_NAME, CHAMPION, version)
    return version


def set_challenger(version: str) -> None:
    _client().set_registered_model_alias(MODEL_NAME, CHALLENGER, version)


def describe(alias: str) -> str:
    found = get_alias(alias)
    if found is None:
        return f"@{alias} not set"
    return f"{MODEL_NAME} v{found[0]} (@{alias}): {found[1].label()}"
