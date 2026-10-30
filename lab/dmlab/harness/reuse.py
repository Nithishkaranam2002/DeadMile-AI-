"""Reuse earlier champion solve runs from MLflow instead of running them again.

A solve run is reused only when everything that defines it matches: the solver
fingerprint (code, configs, solver config, environment; see fingerprint.py),
instance, seed, time limit, data version, and number of workers (so the run
had the same share of the machine). Only runs from a clean tree
(git_dirty = false) are reused. Missing runs are solved fresh. Only the
champion config is ever reused; the candidate always runs fresh.

Caveat, stated on the report card: reused runs ran at another time, under
whatever else the machine was doing then. For solvers that stop at a time
limit, machine load changes how far the search gets. ``--audit-reuse`` re-solves
a sample of reused runs to check that the fingerprint misses nothing.
"""

from typing import Any

from mlflow import MlflowClient

from dmlab.harness.runners import SolverConfig

# Tags written on every harness solve run (see evaluate.py), used for lookup.
TAG_FINGERPRINT = "solver_fingerprint"
TAG_CONFIG = "harness_config_key"  # information only
TAG_INSTANCE = "harness_instance"
TAG_WORKERS = "harness_workers"
TAG_TIME_LIMIT = "harness_time_limit_s"


def reuse_tags(
    config: SolverConfig, fingerprint: str, instance: str, workers: int, time_limit_s: float
) -> dict[str, str]:
    return {
        TAG_FINGERPRINT: fingerprint,
        TAG_CONFIG: config.key(),
        TAG_INSTANCE: instance,
        TAG_WORKERS: str(workers),
        TAG_TIME_LIMIT: f"{time_limit_s:g}",
    }


def find_reusable(
    experiment_id: str,
    fingerprint: str,
    git: dict[str, Any],
    workers: int,
    time_limit_s: float,
    wanted: dict[tuple[str, int], str],
) -> dict[tuple[str, int], Any]:
    """Earlier solve runs for (instance, seed) keys in ``wanted``.

    ``wanted`` maps (instance, seed) to the instance's current data version.
    Returns the newest matching finished run per key. Nothing is reused while
    the tree is dirty, and nothing from runs made on a dirty tree.
    """
    if git["dirty"] or not wanted:
        return {}
    flt = (
        "tags.run_kind = 'solve' and attributes.status = 'FINISHED' "
        f"and tags.{TAG_FINGERPRINT} = '{fingerprint}' and tags.git_dirty = 'false' "
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
