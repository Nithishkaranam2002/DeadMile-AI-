"""compare, report card, registry aliases and self check, end to end on the
tiny Solomon fixture with a temporary SQLite MLflow store (no server, no
downloads). Values are fixtures, not results."""

import json
from pathlib import Path

import mlflow
import pytest
from mlflow import MlflowClient

from dmlab.harness import registry
from dmlab.harness.compare import compare
from dmlab.harness.evaluate import EXPERIMENT, EvalSpec, plan_tasks
from dmlab.harness.runners import LocalRunner, SolverConfig
from dmlab.harness.selfcheck import run_selfcheck
from dmlab.harness.suites import Suite
from dmlab.routing.runner import InstanceRef
from tests.conftest import TINY_SOLOMON


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MlflowClient:
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)
    monkeypatch.setenv("DMLAB_ALLOW_LOCAL_TRACKING", "1")
    monkeypatch.setenv("MLFLOW_DISABLE_AGENT_HINT", "1")
    client = MlflowClient(tracking_uri=uri)
    for name in (EXPERIMENT, registry.REGISTRY_EXPERIMENT):
        client.create_experiment(name, artifact_location=(tmp_path / name).as_uri())
    yield client
    mlflow.set_tracking_uri(None)


def _suite(seeds=(1, 2)) -> Suite:
    ref = InstanceRef("fixture", str(TINY_SOLOMON))
    return Suite.from_refs("quick", "validation", [ref], list(seeds), 1.0)


def test_seedless_solvers_run_once():
    suite = _suite((1, 2, 3))
    tasks = plan_tasks(
        [
            EvalSpec(group="champion", config=SolverConfig(solver="pyvrp"), seeds=[1, 2, 3]),
            EvalSpec(group="candidate", config=SolverConfig(solver="ortools"), seeds=[1, 2, 3]),
        ],
        suite,
    )
    assert [(t.group, t.seed) for t in tasks] == [
        ("champion", 1),
        ("candidate", 1),
        ("champion", 2),
        ("champion", 3),
    ]


def test_pyvrp_refuses_unwired_params():
    with pytest.raises(ValueError):
        _ = SolverConfig(solver="pyvrp", params={"history_length": 10}).uses_seed


def test_compare_logs_report_card(store: MlflowClient):
    c, run_id = compare(
        SolverConfig(solver="nn"), SolverConfig(solver="pyvrp"), _suite(), LocalRunner(2)
    )
    assert c.overall.instances == 1
    assert c.candidate.seeds_run == [1] and c.champion.seeds_run == [1, 2]
    arts = {a.path for a in store.list_artifacts(run_id)}
    assert {"report_card.md", "report_card.json"} <= arts
    run = store.get_run(run_id)
    md = mlflow.artifacts.load_text(f"{run.info.artifact_uri}/report_card.md")
    card = json.loads(mlflow.artifacts.load_text(f"{run.info.artifact_uri}/report_card.json"))
    assert "## In plain words" in md and "## Per slice" in md and "once per instance" in md
    assert card["comparison"]["wilcoxon"]["p_greater"] == run.data.metrics["wilcoxon_p_greater"]
    assert card["provenance"]["git_commit"] == run.data.tags["git_commit"]
    children = store.search_runs([run.info.experiment_id], filter_string="tags.run_kind = 'solve'")
    assert len(children) == 3  # pyvrp x 2 seeds + nn x 1


def test_registry_aliases(store: MlflowClient):
    assert registry.get_alias(registry.CHAMPION) is None
    v = registry.bootstrap_champion(SolverConfig(solver="pyvrp"))
    version, cfg = registry.get_alias(registry.CHAMPION)
    assert version == v and cfg == SolverConfig(solver="pyvrp")
    with pytest.raises(RuntimeError):
        registry.bootstrap_champion(SolverConfig(solver="pyvrp"))
    v2 = registry.register(SolverConfig(solver="ortools"), "test challenger")
    registry.set_challenger(v2)
    assert registry.get_alias(registry.CHALLENGER)[1].solver == "ortools"
    assert registry.get_alias(registry.CHAMPION)[0] == v
    mv = store.get_model_version(registry.MODEL_NAME, v)
    data = mlflow.artifacts.load_dict(f"{mv.source}/{registry.CONFIG_ARTIFACT}")
    assert data["effective_defaults"]["library"].startswith("pyvrp 0.14")


def test_selfcheck_runs_end_to_end(store: MlflowClient):
    checks, comparisons, run_id = run_selfcheck(
        SolverConfig(solver="pyvrp"), SolverConfig(solver="nn"), _suite(), [3, 4], LocalRunner(2)
    )
    assert [c.name.split(":")[0] for c in checks][0] == "A/A"
    assert set(comparisons) == {"aa", "vs_nn"}
    arts = {a.path for a in store.list_artifacts(run_id)}
    assert {"selfcheck.json", "aa", "vs_nn"} <= arts
    with pytest.raises(ValueError):
        run_selfcheck(
            SolverConfig(solver="pyvrp"), SolverConfig(solver="nn"), _suite(), [2], LocalRunner(1)
        )
