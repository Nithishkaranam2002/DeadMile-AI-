"""Run one experiment agent cycle: one MLflow parent run in experiment "agent",
one child run per variant (with its quick evaluation, and its confirmation
nested under it), champion baseline runs, every LLM prompt and response as an
artifact, and the cycle report.

The parent run is created with the MLflow client and never made the active
run, so every node opens its own child runs explicitly (``parent_run_id``),
whichever thread LangGraph runs it in.

Reproducibility: seeds, time limits and suite fingerprints are logged as
params, git commit and dirty flag as tags, data versions on every solve run.
"""

import json
import traceback
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import mlflow
from mlflow import MlflowClient

from dmlab.agent.budgets import BudgetLimits, BudgetTracker
from dmlab.agent.graph import Node, build_graph
from dmlab.agent.llm import LLMClient, redact
from dmlab.agent.memory import ExperimentMemory
from dmlab.agent.state import CycleContext, CycleState
from dmlab.harness import registry
from dmlab.harness.runners import Runner, SolverConfig
from dmlab.harness.suites import Suite
from dmlab.tracking import configure_mlflow, git_info

AGENT_EXPERIMENT = "agent"


def new_cycle_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]


def session_usage(client: MlflowClient, experiment_id: str, session: str) -> tuple[int, float]:
    """LLM tokens and USD already used by earlier cycles of a session."""
    runs = client.search_runs(
        [experiment_id],
        filter_string=f"tags.run_kind = 'agent_cycle' and tags.agent_session = '{session}'",
        max_results=1000,
    )
    tokens = sum(int(r.data.metrics.get("llm_tokens_total", 0)) for r in runs)
    usd = sum(float(r.data.metrics.get("llm_cost_usd", 0.0)) for r in runs)
    return tokens, usd


def enable_tracing() -> str:
    """MLflow tracing of the graph (langchain autolog covers LangGraph) and of
    LiteLLM calls. Returns a note for the run; failure never stops a cycle."""
    notes = []
    for name in ("langchain", "litellm"):
        try:
            getattr(mlflow, name).autolog()
            notes.append(f"{name}: on")
        except Exception as exc:  # tracing is optional
            notes.append(f"{name}: off ({type(exc).__name__}: {exc})")
    return "; ".join(notes)


def run_cycle(
    *,
    llm: LLMClient,
    memory: ExperimentMemory,
    runner: Runner,
    quick_suite: Suite,
    full_suite: Suite,
    session: str | None = None,
    offline: bool = False,
    quick_only: bool = False,
    confirm_top: int = 2,
    tail: Sequence[Node] = (),
    tracing: bool = True,
) -> dict[str, Any]:
    configure_mlflow()
    exp_id = mlflow.set_experiment(AGENT_EXPERIMENT).experiment_id
    client = MlflowClient()
    git = git_info().model_dump()
    cycle_id = new_cycle_id()
    session = session or f"s-{cycle_id}"
    limits = BudgetLimits.load()
    tracker = BudgetTracker(limits, *session_usage(client, exp_id, session))

    found = registry.get_alias(registry.CHAMPION)
    if found is None:
        raise RuntimeError("no @champion in the registry; run `dmlab-harness register-champion`")
    version, champ = found
    champion = _champion_info(version, champ)

    run = client.create_run(
        exp_id,
        run_name=f"agent cycle {cycle_id}",
        tags={
            "run_kind": "agent_cycle",
            "dmlab_module": "3",
            "agent_cycle": cycle_id,
            "agent_session": session,
            "llm_model": llm.model,
            "llm_offline": str(offline).lower(),
            "champion": champion["ref"],
            "git_commit": git["commit"],
            "git_dirty": str(git["dirty"]).lower(),
        },
    )
    run_id = run.info.run_id
    client.log_batch(
        run_id,
        params=[
            mlflow.entities.Param(k, str(v))
            for k, v in {
                "llm_model": llm.model,
                "offline": offline,
                "quick_only": quick_only,
                "confirm_top": confirm_top,
                "session": session,
                "quick.split": quick_suite.split,
                "quick.seeds": ",".join(map(str, quick_suite.seeds)),
                "quick.time_limit_s": quick_suite.time_limit_s,
                "quick.fingerprint": quick_suite.fingerprint(),
                "full.split": full_suite.split,
                "full.seeds": ",".join(map(str, full_suite.seeds)),
                "full.time_limit_s": full_suite.time_limit_s,
                "full.fingerprint": full_suite.fingerprint(),
                "workers": getattr(runner, "workers", "n/a"),
            }.items()
        ],
    )
    client.log_dict(run_id, tracker.snapshot(), "budgets_at_start.json")
    if git["dirty"]:
        client.log_text(run_id, "\n".join(git["changed_files"]), "git_changed_files.txt")
    client.set_tag(run_id, "tracing", enable_tracing() if tracing else "off (disabled)")
    print(f"Agent cycle {cycle_id} (session {session}), model {llm.model}, MLflow run {run_id}")
    print(f"Champion: {champion['ref']}: {champion['label']}")

    state = CycleState(
        cycle_id=cycle_id,
        session=session,
        model=llm.model,
        offline=offline,
        quick_only=quick_only,
        confirm_top=confirm_top,
        champion=champion,
    )
    ctx = CycleContext(
        llm=llm,
        memory=memory,
        runner=runner,
        budget=tracker,
        quick_suite=quick_suite,
        full_suite=full_suite,
        cycle_run_id=run_id,
        experiment_id=exp_id,
        git=git,
        champion_ref=champion["ref"],
    )
    graph = build_graph(tail=tail)
    try:
        out = graph.invoke(
            state,
            config={"configurable": {"thread_id": cycle_id}, "recursion_limit": 100},
            context=ctx,
        )
    except Exception:
        client.log_text(run_id, redact(traceback.format_exc()), "error.txt")
        client.set_terminated(run_id, "FAILED")
        raise
    finally:
        client.log_text(run_id, redact("\n".join(ctx.log)), "cycle_log.txt")
    rep = out["report"]
    used = rep["budgets"]["used"]
    client.log_batch(
        run_id,
        metrics=[
            mlflow.entities.Metric(k, float(v), int(datetime.now(UTC).timestamp() * 1000), 0)
            for k, v in {
                "variants_proposed": rep["variants_proposed"],
                "variants_rejected": rep["variants_rejected"],
                "cpu_minutes": used["cpu_minutes"],
                "nominated": 1 if rep["nominee"] else 0,
                "rounds": rep["rounds"],
            }.items()
        ],
    )
    for key in ("stop_reason", "end_reason", "nomination_note"):
        if rep.get(key):
            client.set_tag(run_id, key, str(rep[key])[:5000])
    if rep["nominee"]:
        client.set_tag(run_id, "nominee", json.dumps(rep["nominee"]))
    client.set_terminated(run_id, "FINISHED")
    return rep


def _champion_info(version: str, config: SolverConfig) -> dict[str, Any]:
    return {
        "version": version,
        "ref": f"{registry.MODEL_NAME} v{version} (@{registry.CHAMPION})",
        "label": config.label(),
        "key": config.key(),
        "config": config.model_dump(),
        "effective_defaults": registry.effective_defaults(config),
    }
