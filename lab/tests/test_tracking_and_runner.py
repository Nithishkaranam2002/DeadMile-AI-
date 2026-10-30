"""Tracking URI guard, git provenance, a small batch and the summary.

Uses a temporary SQLite MLflow store (opted in with DMLAB_ALLOW_LOCAL_TRACKING),
so no server is needed. Values are fixtures, not results.
"""

from pathlib import Path

import mlflow
import pytest
from mlflow import MlflowClient

from dmlab.routing.runner import EXPERIMENT, resolve_instances, run_batch
from dmlab.routing.summary import build_rows, fetch_runs, sanity_problems, to_markdown
from dmlab.tracking import DEFAULT_TRACKING_URI, git_info, tracking_uri
from tests.conftest import TINY_SOLOMON


def test_default_uri_is_lab_server(monkeypatch):
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    assert tracking_uri() == DEFAULT_TRACKING_URI == "http://localhost:5050"


@pytest.mark.parametrize("uri", ["file:///tmp/mlruns", "mlruns", "sqlite:///x.db"])
def test_local_uris_are_refused(monkeypatch, uri):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)
    monkeypatch.delenv("DMLAB_ALLOW_LOCAL_TRACKING", raising=False)
    with pytest.raises(RuntimeError):
        tracking_uri()


def test_git_info():
    info = git_info()
    assert len(info.commit) == 40 and isinstance(info.dirty, bool)


@pytest.fixture
def local_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)
    monkeypatch.setenv("DMLAB_ALLOW_LOCAL_TRACKING", "1")
    monkeypatch.setenv("MLFLOW_DISABLE_AGENT_HINT", "1")
    # Create the experiment with a tmp artifact root so nothing lands in ./mlruns.
    MlflowClient(tracking_uri=uri).create_experiment(
        EXPERIMENT, artifact_location=(tmp_path / "artifacts").as_uri()
    )
    yield uri
    mlflow.set_tracking_uri(None)


def test_batch_logs_runs_and_summary(local_store):
    refs = resolve_instances(f"file:{TINY_SOLOMON}")
    out = run_batch(["nn", "pyvrp"], refs, 1.0, seed=1, workers=1, campaign="test")
    assert len(out) == 2 and not any("error" in r for r in out)

    runs = fetch_runs("test")
    assert {r["tags"]["solver"] for r in runs} == {"nn", "pyvrp"}
    for r in runs:
        assert r["tags"]["git_commit"] and r["tags"]["git_dirty"] in ("true", "false")
        assert r["metrics"]["feasible"] == 1.0
        client = MlflowClient()
        params = client.get_run(r["run_id"]).data.params
        assert params["seed"] == "1" and params["time_limit_s"] == "1.0"
        arts = {a.path for a in client.list_artifacts(r["run_id"])}
        assert {"solution.json", "feasibility.json", "instance.json"} <= arts

    rows = build_rows(runs)
    assert [r["solver"] for r in rows] == ["pyvrp", "nn"]
    assert sanity_problems(runs, rows) == []
    assert "| pyvrp | fixture | 1/1 |" in to_markdown("test", rows, [])


def test_negative_gap_is_flagged():
    runs = [
        {
            "run_id": "x",
            "tags": {"solver": "pyvrp", "instance": "C101", "source": "solomon", "slice": "C1"},
            "metrics": {
                "feasible": 1.0,
                "gap_to_bks_pct": -0.5,
                "total_distance": 823.2,
                "runtime_s": 30.0,
                "vehicles_used": 10,
            },
        }
    ]
    problems = sanity_problems(runs, build_rows(runs))
    assert any("negative gap" in p for p in problems)
