"""Experiment agent cycles end to end with a fake LLM (fixed answers), the tiny
Solomon fixture, a temporary SQLite MLflow store and in-memory Qdrant. No real
LLM, no server, no downloads. Values are fixtures, not results."""

import json
from pathlib import Path

import mlflow
import pytest
from mlflow import MlflowClient
from qdrant_client import QdrantClient

from dmlab.agent import nodes
from dmlab.agent.budgets import BudgetLimits, BudgetTracker
from dmlab.agent.cycle import AGENT_EXPERIMENT, run_cycle
from dmlab.agent.llm import FakeLLM
from dmlab.agent.memory import ExperimentMemory, HashEmbedder
from dmlab.agent.state import CycleContext, CycleState, EvalSummary, VariantRecord
from dmlab.harness import registry
from dmlab.harness.evaluate import EXPERIMENT
from dmlab.harness.runners import LocalRunner, SolverConfig
from dmlab.harness.suites import Suite
from dmlab.routing.runner import InstanceRef
from tests.conftest import TINY_SOLOMON

REF = InstanceRef("fixture", str(TINY_SOLOMON))
SECRET = "sk-fake-secret-value-123456"

BASE = {
    "hypothesis": "a shorter late acceptance history converges faster",
    "rationale": "the quick suite has a short time limit",
    "expected_effect": "shorter total distance",
}
GOOD_PARAM = {
    "kind": "parameter",
    "solver": "pyvrp",
    "name": "short history",
    **BASE,
    "pyvrp": {"ils": {"history_length": 50}},
}
GOOD_FORM = {
    "kind": "formulation",
    "name": "reserve capacity",
    **BASE,
    "formulation": {"capacity_reserve_share": 0.1},
}
CODE = {"kind": "code", "name": "my clustering", **BASE, "plugin": "stop_clustering", "source": "x"}
TIME = {**GOOD_PARAM, "name": "more time", "time_limit_s": 60}
BAD = {**GOOD_PARAM, "name": "bad history", "pyvrp": {"ils": {"history_length": 0}}}
HYP = {
    "hypotheses": [
        {
            "statement": "shorter history helps in short runs",
            "reasoning": "late acceptance with a long history wanders too long",
            "variant_kind": "parameter",
        }
    ]
}


def reflection(vids: list[str], go_on: bool = False) -> dict:
    return {
        "lessons": [{"vid": v, "lesson": f"lesson for {v}"} for v in vids],
        "continue_search": go_on,
        "reason": "enough for this test",
    }


@pytest.fixture
def lab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)
    monkeypatch.setenv("DMLAB_ALLOW_LOCAL_TRACKING", "1")
    monkeypatch.setenv("MLFLOW_DISABLE_AGENT_HINT", "1")
    monkeypatch.setenv("DMLAB_FAKE_API_KEY", SECRET)
    client = MlflowClient(tracking_uri=uri)
    for name in (EXPERIMENT, registry.REGISTRY_EXPERIMENT, AGENT_EXPERIMENT):
        client.create_experiment(name, artifact_location=(tmp_path / name).as_uri())
    registry.bootstrap_champion(SolverConfig(solver="pyvrp"))
    memory = ExperimentMemory(QdrantClient(":memory:"), HashEmbedder())
    yield client, memory, tmp_path, monkeypatch
    mlflow.set_tracking_uri(None)


def budgets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **over) -> None:
    values = {
        "wall_clock_seconds": 60,
        "max_variants": 8,
        "max_cpu_minutes": 30,
        "llm_max_tokens": 100_000,
        "llm_max_usd": 1.0,
    } | over
    path = tmp_path / "budgets.yaml"
    path.write_text(
        f"per_run:\n  wall_clock_seconds: {values['wall_clock_seconds']}\n"
        f"per_cycle:\n  max_variants: {values['max_variants']}\n"
        f"  max_cpu_minutes: {values['max_cpu_minutes']}\n"
        f"per_session:\n  llm_max_tokens: {values['llm_max_tokens']}\n"
        f"  llm_max_usd: {values['llm_max_usd']}\n"
    )
    monkeypatch.setenv("DMLAB_BUDGETS_FILE", str(path))


def suites(limit: float = 0.2) -> tuple[Suite, Suite]:
    return (
        Suite.from_refs("quick", "tune", [REF], [1, 2], limit),
        Suite.from_refs("full", "validation", [REF], [1, 2], limit),
    )


def cycle(memory, llm, **kw):
    quick, full = suites(kw.pop("limit", 0.2))
    return run_cycle(
        llm=llm,
        memory=memory,
        runner=LocalRunner(2),
        quick_suite=quick,
        full_suite=full,
        tracing=False,
        **kw,
    )


def artifacts_text(client: MlflowClient, run_id: str, tmp_path: Path) -> str:
    out = Path(mlflow.artifacts.download_artifacts(run_id=run_id, dst_path=str(tmp_path / "dl")))
    return "\n".join(p.read_text() for p in out.rglob("*") if p.is_file())


def test_cycle_screens_runs_and_reports(lab):
    client, memory, tmp_path, mp = lab
    budgets(tmp_path, mp)
    llm = FakeLLM(
        {
            "HypothesisSet": [HYP],
            "ProposalBatch": [{"variants": [GOOD_PARAM, GOOD_FORM, CODE, TIME, BAD]}],
            "Reflection": [reflection(["v01", "v02", "v03", "v04", "v05"])],
        }
    )
    rep = cycle(memory, llm, confirm_top=1)
    by = {r["vid"]: r for r in rep["ranked"]}
    assert len(by) == 5 and rep["variants_rejected"] == 3
    assert "disabled until Module 4" in by["v03"]["reason"]
    assert "time limit" in by["v04"]["reason"]
    assert "schema validation failed" in by["v05"]["reason"]
    for vid in ("v01", "v02"):
        assert by[vid]["status"] in {"not_better", "promising", "infeasible", "not_confirmed"}
        assert by[vid]["quick"]["split"] == "tune"
        assert by[vid]["mlflow_run_id"]
    assert rep["model"]["name"] == "fake/fixed-answers"
    assert rep["nominee"] is None  # one instance can never pass the gate checks
    assert rep["stop_reason"] is None
    # Memory holds the screened variants and the code variant, with lessons.
    assert memory.count() == 3
    # The formulation variant was measured on the original instance.
    form_run = client.get_run(by["v02"]["mlflow_run_id"])
    assert form_run.data.tags["run_kind"] == "agent_variant"
    # Parent run, child runs, artifacts.
    parent = rep["mlflow_cycle_run_id"]
    arts = {a.path for a in client.list_artifacts(parent)}
    assert {"cycle_report.json", "cycle_report.md", "llm"} <= arts
    llm_arts = {a.path for a in client.list_artifacts(parent, "llm")}
    assert any(p.endswith("_propose_prompt.md") for p in llm_arts)
    children = client.search_runs(
        [client.get_experiment_by_name(AGENT_EXPERIMENT).experiment_id],
        filter_string=f"tags.mlflow.parentRunId = '{parent}' and tags.run_kind = 'agent_variant'",
    )
    assert len(children) == 2
    assert client.get_run(parent).data.metrics["llm_tokens_total"] == 3 * 1500


def test_second_cycle_rejects_exact_repeats(lab):
    client, memory, tmp_path, mp = lab
    budgets(tmp_path, mp)
    answers = {
        "HypothesisSet": [HYP],
        "ProposalBatch": [{"variants": [GOOD_PARAM]}],
        "Reflection": [reflection(["v01"])],
    }
    cycle(memory, FakeLLM(answers), quick_only=True)
    rep = cycle(memory, FakeLLM(answers), quick_only=True)
    (row,) = rep["ranked"]
    assert row["status"] == "rejected" and "already tested" in row["reason"]


def test_variant_cap_rejects_extra_proposals(lab):
    _, memory, tmp_path, mp = lab
    budgets(tmp_path, mp, max_variants=2)
    llm = FakeLLM(
        {
            "HypothesisSet": [HYP],
            "ProposalBatch": [{"variants": [GOOD_PARAM, GOOD_FORM, CODE]}],
            "Reflection": [reflection(["v01", "v02", "v03"], go_on=True)],
        }
    )
    rep = cycle(memory, llm, quick_only=True)
    by = {r["vid"]: r for r in rep["ranked"]}
    assert "variant cap" in by["v03"]["reason"]
    assert rep["end_reason"].startswith("variant cap reached")


def test_llm_dollar_budget_stops_cleanly(lab):
    client, memory, tmp_path, mp = lab
    budgets(tmp_path, mp, llm_max_usd=0.0005)
    rep = cycle(memory, FakeLLM({"HypothesisSet": [HYP]}, usd_per_call=0.001))
    assert rep["stop_reason"].startswith("LLM dollar budget")
    assert rep["nominee"] is None and rep["variants_proposed"] == 0
    run = client.get_run(rep["mlflow_cycle_run_id"])
    assert run.info.status == "FINISHED"
    assert run.data.tags["stop_reason"].startswith("LLM dollar budget")


def test_llm_token_budget_counts_the_whole_session(lab):
    _, memory, tmp_path, mp = lab
    budgets(tmp_path, mp, llm_max_tokens=4000)
    answers = {
        "HypothesisSet": [HYP],
        "ProposalBatch": [{"variants": [GOOD_PARAM]}],
        "Reflection": [reflection(["v01"])],
    }
    # Each fake call uses (and may use at most) 1500 tokens: hypothesize and
    # propose fit (3000), reflect would reach 4500 and is refused before it runs.
    first = cycle(memory, FakeLLM(answers), quick_only=True, session="s1")
    assert first["stop_reason"].startswith("LLM token budget")
    assert first["budgets"]["used"]["session_llm_tokens"] == 3000
    # The variant still ran and was stored, without a lesson.
    (row,) = first["ranked"]
    assert row["quick"] is not None and row["lesson"] is None
    # A second cycle of the same session starts at 3000 and stops at once.
    second = cycle(memory, FakeLLM(answers), quick_only=True, session="s1")
    assert second["stop_reason"].startswith("LLM token budget")
    assert second["variants_proposed"] == 0


def test_cpu_budget_stops_before_running(lab):
    _, memory, tmp_path, mp = lab
    budgets(tmp_path, mp, max_cpu_minutes=0.001)
    llm = FakeLLM(
        {"HypothesisSet": [HYP], "ProposalBatch": [{"variants": [GOOD_PARAM]}], "Reflection": []}
    )
    rep = cycle(memory, llm)
    assert rep["stop_reason"].startswith("CPU budget")
    (row,) = rep["ranked"]
    assert row["status"] == "rejected" and row["reason"].startswith("not run: CPU budget")


def test_wall_clock_budget_stops_the_cycle(lab):
    _, memory, tmp_path, mp = lab
    budgets(tmp_path, mp, wall_clock_seconds=0.3)
    llm = FakeLLM(
        {"HypothesisSet": [HYP], "ProposalBatch": [{"variants": [GOOD_PARAM]}], "Reflection": []}
    )
    rep = cycle(memory, llm, limit=3.0)
    assert "wall clock" in rep["stop_reason"]
    assert rep["nominee"] is None


def test_keys_never_reach_artifacts(lab):
    client, memory, tmp_path, mp = lab
    budgets(tmp_path, mp)
    leaky = json.loads(json.dumps(HYP))
    leaky["hypotheses"][0]["reasoning"] = f"the key is {SECRET} and should never be logged"
    llm = FakeLLM({"HypothesisSet": [leaky], "ProposalBatch": [{"variants": []}], "Reflection": []})
    rep = cycle(memory, llm, quick_only=True)
    text = artifacts_text(client, rep["mlflow_cycle_run_id"], tmp_path)
    assert "[REDACTED]" in text
    assert SECRET not in text


def test_nominate_sets_challenger_only_for_a_confirmed_variant(lab):
    client, memory, tmp_path, mp = lab
    budgets(tmp_path, mp)
    exp = client.get_experiment_by_name(AGENT_EXPERIMENT).experiment_id
    parent = client.create_run(exp).info.run_id
    child = client.create_run(exp).info.run_id
    champ = SolverConfig(solver="pyvrp")
    cand = SolverConfig(solver="pyvrp", params={"ils": {"history_length": 50}})
    summary = EvalSummary(
        suite="full",
        split="validation",
        time_limit_s=1,
        seeds=[1],
        instances=1,
        candidate_runs=1,
        candidate_feasible_runs=1,
        candidate_feasible_instances=1,
        paired=1,
        excluded=0,
        wins=1,
        losses=0,
        ties=0,
        median_rel_improvement=0.01,
        ci_low=0.005,
        ci_high=0.02,
        p_two_sided=0.01,
        runtime_ratio=1.0,
        slices=[],
        champion_reused_runs=0,
        champion_total_runs=1,
        cpu_seconds=1,
        run_id=child,
        gate_checks=[],
        gate_checks_met=True,
    )  # fixture numbers, not results
    rec = VariantRecord(
        vid="v01",
        round=1,
        status="confirmed",
        reason="fixture",
        name="short",
        variant={},
        config=cand.model_dump(),
        config_key=cand.key(),
        config_label=cand.label(),
        run_id=child,
        quick=summary,
        full=summary,
    )
    state = CycleState(
        cycle_id="c",
        session="s",
        model="fake",
        offline=False,
        quick_only=False,
        confirm_top=1,
        champion={"config": champ.model_dump(), "key": champ.key()},
        variants=[rec],
    )
    ctx = CycleContext(
        llm=FakeLLM({}),
        memory=memory,
        runner=LocalRunner(1),
        budget=BudgetTracker(BudgetLimits.load()),
        quick_suite=suites()[0],
        full_suite=suites()[1],
        cycle_run_id=parent,
        experiment_id=exp,
        git={"commit": "x", "dirty": True},
    )

    class RT:
        context = ctx

    out = nodes.nominate(state, RT())
    assert out["nominee"]["vid"] == "v01"
    version, config = registry.get_alias(registry.CHALLENGER)
    assert config.key() == cand.key() and version == out["nominee"]["version"]
    assert registry.get_alias(registry.CHAMPION)[1].key() == champ.key()  # unchanged

    rec.status = "not_confirmed"
    none = nodes.nominate(state.model_copy(update={"variants": [rec]}), RT())
    assert none["nominee"] is None and "valid result" in none["nomination_note"]
