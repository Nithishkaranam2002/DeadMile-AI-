"""Reuse earlier champion solve runs from MLflow instead of running them again.

A solve run is reused only when everything that defines it matches:
solver config key, git commit (from a clean tree, git_dirty = false),
instance, seed, time limit, data version, and number of workers (so the run
had the same share of the machine). Missing runs are solved fresh. Only the
champion config is ever reused; the candidate always runs fresh.

Caveat, stated on the report card: reused runs ran at another time, under
whatever else the machine was doing then. For solvers that stop at a time
limit, machine load changes how far the search gets.
"""

from typing import Any

from mlflow import MlflowClient

from dmlab.harness.runners import SolverConfig

# Tags written on every harness solve run (see evaluate.py), used for lookup.
TAG_CONFIG = "harness_config_key"
TAG_INSTANCE = "harness_instance"
TAG_WORKERS = "harness_workers"
TAG_TIME_LIMIT = "harness_time_limit_s"


def reuse_tags(config: SolverConfig, instance: str, workers: int, time_limit_s: float) -> dict:
    return {
        TAG_CONFIG: config.key(),
        TAG_INSTANCE: instance,
        TAG_WORKERS: str(workers),
        TAG_TIME_LIMIT: f"{time_limit_s:g}",
    }


def find_reusable(
    experiment_id: str,
    config: SolverConfig,
    git: dict[str, Any],
    workers: int,
    time_limit_s: float,
    wanted: dict[tuple[str, int], str],
) -> dict[tuple[str, int], Any]:
    """Earlier solve runs for (instance, seed) keys in ``wanted``.

    ``wanted`` maps (instance, seed) to the instance's current data version.
    Returns the newest matching finished run per key. Nothing is reused from a
    dirty tree, because its commit hash does not identify the code.
    """
    if git["dirty"] or not wanted:
        return {}
    flt = (
        "tags.run_kind = 'solve' and attributes.status = 'FINISHED' "
        f"and tags.{TAG_CONFIG} = '{config.key()}' "
        f"and tags.git_commit = '{git['commit']}' and tags.git_dirty = 'false' "
        f"and tags.{TAG_WORKERS} = '{workers}' "
        f"and tags.{TAG_TIME_LIMIT} = '{time_limit_s:g}'"
    )
    runs = MlflowClient().search_runs(
        [experiment_id],
        filter_string=flt,
        max_results=50_000,
        order_by=["attributes.start_time DESC"],
    )
    found: dict[tuple[str, int], Any] = {}
    for r in runs:  # newest first
        key = (r.data.tags.get(TAG_INSTANCE), int(r.data.params.get("seed", -1)))
        if key in wanted and key not in found and r.data.tags.get("data_version") == wanted[key]:
            found[key] = r
    return found
