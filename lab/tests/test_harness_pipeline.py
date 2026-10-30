"""compare, report card, registry aliases and self check, end to end on the
tiny Solomon fixture with a temporary SQLite MLflow store (no server, no
downloads). Values are fixtures, not results."""

import json
from pathlib import Path

import mlflow
import pytest
from mlflow import MlflowClient

from dmlab.harness import compare as compare_module
from dmlab.harness import registry
from dmlab.harness.compare import compare
from dmlab.harness.evaluate import EXPERIMENT, EvalSpec, plan_tasks
from dmlab.harness.runners import LocalRunner, SolverConfig
from dmlab.harness.selfcheck import run_selfcheck
from dmlab.harness.suites import Suite
from dmlab.routing.runner import InstanceRef
from dmlab.tracking import GitInfo
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
    assert "## Gate thresholds (information only)" in md and "## Fair runs" in md
    assert "## Other metrics (information only" in md
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
    assert checks[0].name.startswith("A/A") and checks[0].rule.startswith("two sided")
    assert set(comparisons) == {"aa", "vs_nn"}
    assert comparisons["aa"].candidate.seeds_run == [3, 4]
    assert comparisons["aa"].champion.seeds_run == [1, 2]
    arts = {a.path for a in store.list_artifacts(run_id)}
    assert {"selfcheck.json", "report_card_runs.json"} <= arts
    exp = store.get_run(run_id).info.experiment_id
    named = store.search_runs(
        [exp], filter_string="attributes.run_name = 'A/A check: champion vs itself'"
    )
    assert len(named) == 1
    card = mlflow.artifacts.load_text(f"{named[0].info.artifact_uri}/report_card.md")
    assert card.startswith("# A/A check: champion vs itself") and "Luck test" in card
    with pytest.raises(ValueError):
        run_selfcheck(
            SolverConfig(solver="pyvrp"), SolverConfig(solver="nn"), _suite(), [2], LocalRunner(1)
        )


@pytest.fixture
def clean_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reuse needs a clean tree; pretend the tree is clean at a fixed commit."""
    fake = GitInfo(commit="f" * 40, dirty=False, changed_files=[])
    monkeypatch.setattr(compare_module, "git_info", lambda: fake)


def test_champion_runs_are_reused(store: MlflowClient, clean_git: None):
    nn, pyvrp = SolverConfig(solver="nn"), SolverConfig(solver="pyvrp")
    first, _ = compare(nn, pyvrp, _suite(), LocalRunner(2))
    assert first.champion.reused_runs == 0
    second, run_id = compare(nn, pyvrp, _suite(), LocalRunner(2))
    assert second.champion.reused_runs == 2 and second.candidate.reused_runs == 0
    assert sorted(second.champion.reused_run_ids) == sorted(
        r.info.run_id for r in first_champion_runs(store, first)
    )
    assert second.overall.median_rel_improvement == first.overall.median_rel_improvement
    md = mlflow.artifacts.load_text(f"{store.get_run(run_id).info.artifact_uri}/report_card.md")
    assert "2 of 2 solve runs were reused" in md
    # Other worker count or time limit: nothing is reused.
    third, _ = compare(nn, pyvrp, _suite(), LocalRunner(1))
    assert third.champion.reused_runs == 0
    fourth, _ = compare(nn, pyvrp, _suite(), LocalRunner(2), reuse_champion=False)
    assert fourth.champion.reused_runs == 0


def first_champion_runs(store: MlflowClient, c) -> list:
    ev = store.get_run(c.champion.run_id)
    return store.search_runs(
        [ev.info.experiment_id],
        filter_string=f"tags.mlflow.parentRunId = '{c.champion.run_id}'",
    )


def test_no_reuse_from_a_dirty_tree(store: MlflowClient):
    # The real tree may be dirty while developing; force dirty to be sure.
    nn, pyvrp = SolverConfig(solver="nn"), SolverConfig(solver="pyvrp")
    dirty = GitInfo(commit="e" * 40, dirty=True, changed_files=["x"])
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(compare_module, "git_info", lambda: dirty)
        compare(nn, pyvrp, _suite(), LocalRunner(2))
        again, _ = compare(nn, pyvrp, _suite(), LocalRunner(2))
    assert again.champion.reused_runs == 0


def test_reuse_works_across_commits_when_only_excluded_code_changed(store, monkeypatch):
    nn, pyvrp = SolverConfig(solver="nn"), SolverConfig(solver="pyvrp")
    for commit in ("a" * 40, "b" * 40):  # two clean commits, same fingerprint
        fake = GitInfo(commit=commit, dirty=False, changed_files=[])
        monkeypatch.setattr(compare_module, "git_info", lambda fake=fake: fake)
        c, _ = compare(nn, pyvrp, _suite(), LocalRunner(2))
    assert c.champion.reused_runs == 2
    assert c.champion.fingerprint and c.candidate.fingerprint
    assert c.champion.fingerprint != c.candidate.fingerprint


def test_reuse_audit_resolves_reused_runs(store, clean_git):
    nn, pyvrp = SolverConfig(solver="nn"), SolverConfig(solver="pyvrp")
    compare(nn, pyvrp, _suite(), LocalRunner(2))
    c, run_id = compare(nn, pyvrp, _suite(), LocalRunner(2), audit_reuse=1)
    assert c.champion.reused_runs == 2 and len(c.champion.reuse_audit) == 1
    a = c.champion.reuse_audit[0]
    assert a["reused_distance"] is not None and a["fresh_distance"] is not None
    md = mlflow.artifacts.load_text(f"{store.get_run(run_id).info.artifact_uri}/report_card.md")
    assert "Reuse audit (champion): 1 reused runs were solved again" in md
    ev = store.get_run(c.champion.run_id)
    arts = {x.path for x in store.list_artifacts(ev.info.run_id)}
    assert "fingerprint.json" in arts
