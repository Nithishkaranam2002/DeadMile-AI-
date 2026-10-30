"""Screening and confirmation for the experiment agent, built on the Module 2
harness (run_evaluations, compare_evaluations, gate_preview).

* Screening: the quick suite (a tune subset, short time limit).
* Confirmation: the full validation suite at the gate's time limit.

These are the only two suites the agent can build, and neither function takes
a split argument: the agent has no code path that can load the test split.
The time limit always comes from the suite.

Champion evaluations run once per suite per cycle in their own MLflow run
(with champion reuse from earlier runs), and every candidate is compared with
that evaluation. Both run on the same runner and worker count.
"""

from typing import Any

import mlflow

from dmlab.agent.state import EvalSummary
from dmlab.harness.compare import Comparison, compare_evaluations, log_comparison, run_context
from dmlab.harness.compare import statistics_settings as _statistics_settings
from dmlab.harness.evaluate import EvalSpec, Evaluation, plan_tasks, run_evaluations
from dmlab.harness.gate_preview import preview
from dmlab.harness.runners import WALL_CLOCK_ERROR, Runner, SolverConfig
from dmlab.harness.suites import Suite, full_suite, quick_suite


def screening_suite() -> Suite:
    """Quick suite: tune subset, 2 seeds, short time limit."""
    return quick_suite()


def confirmation_suite() -> Suite:
    """Full validation suite at the gate's time limit."""
    return full_suite("validation")


def estimate_cpu_seconds(config: SolverConfig, suite: Suite) -> float:
    """Upper estimate: every task runs to the suite's time limit."""
    tasks = plan_tasks([EvalSpec(group="x", config=config, seeds=suite.seeds)], suite)
    return len(tasks) * suite.time_limit_s


def fresh_cpu_seconds(ev: Evaluation, wall_clock_s: float | None) -> float:
    """Solver time actually spent (reused runs cost nothing)."""
    total = 0.0
    for r in ev.runs:
        if r.reused:
            continue
        if r.runtime_s is not None:
            total += r.runtime_s
        elif r.error and WALL_CLOCK_ERROR in r.error and wall_clock_s:
            total += wall_clock_s
    return total


def evaluate_champion(
    champion: SolverConfig, suite: Suite, runner: Runner, git: dict[str, Any], ref: str | None
) -> Evaluation:
    (ev,) = run_evaluations(
        [
            EvalSpec(
                group="champion", config=champion, seeds=suite.seeds, registry_ref=ref, reuse=True
            )
        ],
        suite,
        runner,
        f"agent champion baseline {suite.name}/{suite.split}",
        git,
    )
    return ev


def evaluate_candidate(
    candidate: SolverConfig,
    champion_eval: Evaluation,
    suite: Suite,
    runner: Runner,
    git: dict[str, Any],
    run_id: str,
    wall_clock_s: float | None,
    with_gate_checks: bool,
) -> tuple[EvalSummary, Comparison]:
    """Evaluate a candidate on the suite (nested under the active run), compare
    with the champion's evaluation, and log the report card on the active run."""
    (ev,) = run_evaluations(
        [EvalSpec(group="candidate", config=candidate, seeds=suite.seeds)],
        suite,
        runner,
        f"agent candidate {candidate.key()} {suite.name}/{suite.split}",
        git,
    )
    c = compare_evaluations(ev, champion_eval, _statistics_settings())
    ctx = run_context(git, run_id, runner)
    ctx["mlflow_experiment"] = "agent"
    log_comparison(c, "", ctx, title=f"{candidate.label()} vs champion, {suite.name}/{suite.split}")
    checks = [g.model_dump() for g in preview(c)] if with_gate_checks else None
    if checks is not None:
        mlflow.log_dict(
            {
                "gate_checks": checks,
                "note": "gate thresholds from gates.yaml, "
                "applied to full validation; the promotion gate itself (test "
                "split, human approval) is Module 4",
            },
            "gate_checks.json",
        )
    o = c.overall
    errors = sorted({r.error for r in ev.runs if r.error})
    summary = EvalSummary(
        suite=suite.name,
        split=suite.split,
        time_limit_s=suite.time_limit_s,
        seeds=ev.seeds_run,
        instances=o.instances,
        candidate_runs=len(ev.runs),
        candidate_feasible_runs=sum(1 for r in ev.runs if r.feasible),
        errors=errors,
        wall_clock_exceeded=any(WALL_CLOCK_ERROR in e for e in errors),
        candidate_feasible_instances=o.candidate_feasible_instances,
        paired=o.paired,
        excluded=o.excluded,
        wins=o.wins,
        losses=o.losses,
        ties=o.ties,
        median_rel_improvement=o.median_rel_improvement,
        ci_low=o.ci_low,
        ci_high=o.ci_high,
        p_two_sided=c.wilcoxon.p_two_sided if c.wilcoxon.n_nonzero else None,
        runtime_ratio=o.runtime_ratio,
        slices=[
            {"slice": s.slice, "median": s.median_rel_improvement, "paired": s.paired}
            for s in c.slices
        ],
        champion_reused_runs=c.champion.reused_runs,
        champion_total_runs=c.champion.total_runs,
        cpu_seconds=fresh_cpu_seconds(ev, wall_clock_s),
        run_id=run_id,
        gate_checks=checks,
        gate_checks_met=all(g["met"] for g in checks) if checks is not None else None,
    )
    return summary, c
