"""Compare a candidate against the champion on a suite.

``compare_evaluations`` is pure: it pairs two evaluations per instance and
computes the statistics. ``compare`` runs both evaluations (tasks interleaved
on one runner), compares them, and logs the report card to MLflow.

Pairing rules:
* seeds are averaged per instance first (seedless solvers have one run);
* an instance enters the distance statistics only when both solvers were
  feasible on every run of it; otherwise it is listed as excluded, with why;
* r = (champion - candidate) / champion, so r > 0 means the candidate is better.

Fair runs: both sides use the same suite, time limit and worker count (checked
here). Champion runs may be reused from MLflow (see reuse.py); the card says
how many. The primary metric is total distance; the other metrics are shown
for information and never used for pass or fail.
"""

from collections import defaultdict
from typing import Any, Literal

import mlflow
from pydantic import BaseModel

from dmlab.harness import stats
from dmlab.harness.evaluate import EXPERIMENT, MODULE, EvalSpec, Evaluation, run_evaluations
from dmlab.harness.runners import Runner, SolverConfig
from dmlab.harness.splits import suite_settings
from dmlab.harness.suites import Suite
from dmlab.tracking import configure_mlflow, git_info

Outcome = Literal["win", "loss", "tie", "excluded"]


class Side(BaseModel):
    group: str
    label: str
    solver: str
    params: dict[str, Any]
    registry_ref: str | None
    seeds_run: list[int]
    seed_policy: str
    run_id: str
    workers: int | None = None
    reused_runs: int = 0
    total_runs: int = 0
    reused_run_ids: list[str] = []


class SideMetrics(BaseModel):
    """Information only: means over instances of seed averaged values."""

    vehicles_used: float | None
    distance_per_stop: float | None
    productivity_name: str | None  # stops_per_driver_hour or stops_per_100_time_units
    productivity: float | None
    time_window_violations: float | None
    cost_per_stop: float | None
    cost_note: str


class SecondaryRow(BaseModel):
    slice: str
    distance_unit: str
    champion: SideMetrics
    candidate: SideMetrics


class PairedInstance(BaseModel):
    instance: str
    slice: str
    source: str
    distance_unit: str
    champion_runs: int
    champion_feasible_runs: int
    candidate_runs: int
    candidate_feasible_runs: int
    champion_distance: float | None  # seed mean, only when all runs are feasible
    candidate_distance: float | None
    champion_runtime_s: float | None  # seed mean over runs that did not crash
    candidate_runtime_s: float | None
    rel_improvement: float | None
    outcome: Outcome
    note: str = ""


class SliceRow(BaseModel):
    slice: str
    instances: int
    paired: int
    excluded: int
    candidate_feasible_instances: int
    champion_feasible_instances: int
    wins: int
    losses: int
    ties: int
    median_rel_improvement: float | None
    ci_low: float | None
    ci_high: float | None
    champion_mean_distance: float | None
    candidate_mean_distance: float | None
    distance_unit: str
    runtime_ratio: float | None


class Comparison(BaseModel):
    candidate: Side
    champion: Side
    suite_name: str
    split: str
    time_limit_s: float
    num_instances: int
    statistics_settings: dict[str, Any]
    overall: SliceRow
    wilcoxon: stats.WilcoxonResult
    slices: list[SliceRow]
    instances: list[PairedInstance]
    labels: dict[str, list[str]]  # source -> honesty labels
    distance_labels: dict[str, str]  # source -> distance label
    data_versions: dict[str, list[str]]  # source -> data versions seen
    secondary: list[SecondaryRow]
    min_p_two_sided: float | None  # smallest two sided p reachable with these pairs
    workers: int | None


def _side(ev: Evaluation) -> Side:
    return Side(
        group=ev.group,
        label=ev.config.label(),
        solver=ev.config.solver,
        params=ev.config.params,
        registry_ref=ev.registry_ref,
        seeds_run=ev.seeds_run,
        seed_policy=ev.seed_policy,
        run_id=ev.run_id,
        workers=ev.workers,
        reused_runs=ev.reused_runs,
        total_runs=len(ev.runs),
        reused_run_ids=ev.reused_run_ids,
    )


def _side_metrics(runs: list[Any]) -> SideMetrics:
    ok = [r for r in runs if not r.error]
    per_inst: dict[str, list[Any]] = defaultdict(list)
    for r in ok:
        per_inst[r.instance].append(r)

    def mean_of(attr: str) -> float | None:
        vals = []
        for rs in per_inst.values():
            xs = [getattr(r, attr) for r in rs if getattr(r, attr) is not None]
            if xs:
                vals.append(stats.seed_mean(xs))
        return stats.seed_mean(vals) if vals else None

    names = {r.productivity_name for r in ok if r.productivity_name}
    # One productivity unit per side and slice; mixed units are not averaged.
    prod_name = next(iter(names)) if len(names) == 1 else None
    notes = sorted({r.cost_note for r in ok if r.cost_note})
    return SideMetrics(
        vehicles_used=mean_of("vehicles_used"),
        distance_per_stop=mean_of("distance_per_stop"),
        productivity_name=prod_name,
        productivity=mean_of("productivity") if prod_name else None,
        time_window_violations=mean_of("time_window_violations"),
        cost_per_stop=mean_of("cost_per_stop"),
        cost_note="; ".join(notes),
    )


def _pair(name: str, champ: list[Any], cand: list[Any]) -> PairedInstance:
    first = (champ or cand)[0]

    def summary(runs: list[Any]) -> tuple[int, int, float | None, float | None]:
        feasible = [r for r in runs if r.feasible and r.total_distance is not None]
        times = [r.runtime_s for r in runs if r.runtime_s is not None]
        dist = (
            stats.seed_mean([r.total_distance for r in runs])
            if (runs and len(feasible) == len(runs))
            else None
        )
        return len(runs), len(feasible), dist, (stats.seed_mean(times) if times else None)

    ch_n, ch_f, ch_d, ch_t = summary(champ)
    ca_n, ca_f, ca_d, ca_t = summary(cand)
    rel, outcome, note = None, "excluded", ""
    if ch_d is None or ca_d is None:
        why = []
        if ch_d is None:
            why.append(f"champion feasible on {ch_f}/{ch_n} runs")
        if ca_d is None:
            why.append(f"candidate feasible on {ca_f}/{ca_n} runs")
        note = "; ".join(why)
    else:
        rel = stats.relative_improvement(ch_d, ca_d)
        outcome = "win" if rel > 0 else "loss" if rel < 0 else "tie"
    return PairedInstance(
        instance=name,
        slice=first.slice,
        source=first.source,
        distance_unit=first.distance_unit,
        champion_runs=ch_n,
        champion_feasible_runs=ch_f,
        candidate_runs=ca_n,
        candidate_feasible_runs=ca_f,
        champion_distance=ch_d,
        candidate_distance=ca_d,
        champion_runtime_s=ch_t,
        candidate_runtime_s=ca_t,
        rel_improvement=rel,
        outcome=outcome,
        note=note,
    )


def _row(slice_name: str, items: list[PairedInstance], st: dict[str, Any]) -> SliceRow:
    paired = [p for p in items if p.rel_improvement is not None]
    r = [p.rel_improvement for p in paired]
    wlt = stats.win_loss_tie(r)
    ci = stats.bootstrap_median_ci(
        r, st["ci_level"], st["bootstrap_resamples"], st["bootstrap_seed"]
    )
    both_t = [
        p for p in items if p.champion_runtime_s is not None and p.candidate_runtime_s is not None
    ]
    ch_t = sum(p.champion_runtime_s for p in both_t)
    units = sorted({p.distance_unit for p in items})
    return SliceRow(
        slice=slice_name,
        instances=len(items),
        paired=len(paired),
        excluded=len(items) - len(paired),
        candidate_feasible_instances=sum(
            1 for p in items if p.candidate_runs and p.candidate_feasible_runs == p.candidate_runs
        ),
        champion_feasible_instances=sum(
            1 for p in items if p.champion_runs and p.champion_feasible_runs == p.champion_runs
        ),
        wins=wlt.wins,
        losses=wlt.losses,
        ties=wlt.ties,
        median_rel_improvement=stats.median(r),
        ci_low=ci[0] if ci else None,
        ci_high=ci[1] if ci else None,
        champion_mean_distance=(
            stats.seed_mean([p.champion_distance for p in paired]) if paired else None
        ),
        candidate_mean_distance=(
            stats.seed_mean([p.candidate_distance for p in paired]) if paired else None
        ),
        distance_unit=units[0] if len(units) == 1 else "mixed units (see slices)",
        runtime_ratio=(sum(p.candidate_runtime_s for p in both_t) / ch_t) if ch_t else None,
    )


def compare_evaluations(
    candidate: Evaluation, champion: Evaluation, settings: dict[str, Any] | None = None
) -> Comparison:
    st = settings or statistics_settings()
    if (candidate.split, candidate.suite_name, candidate.time_limit_s) != (
        champion.split,
        champion.suite_name,
        champion.time_limit_s,
    ):
        raise ValueError("candidate and champion were evaluated on different suites")
    by = {"champion": defaultdict(list), "candidate": defaultdict(list)}
    for side, ev in (("champion", champion), ("candidate", candidate)):
        for run in ev.runs:
            by[side][run.instance].append(run)
    if set(by["champion"]) != set(by["candidate"]):
        raise ValueError("candidate and champion were evaluated on different instances")
    if candidate.workers != champion.workers:
        raise ValueError("candidate and champion must run with the same number of workers")

    order = [*st.get("slice_order", []), "fixture"]
    instances = [
        _pair(name, by["champion"][name], by["candidate"][name]) for name in sorted(by["champion"])
    ]
    slice_names = sorted(
        {p.slice for p in instances}, key=lambda s: (order.index(s) if s in order else 99, s)
    )
    slices = [_row(s, [p for p in instances if p.slice == s], st) for s in slice_names]
    secondary = []
    for s in slice_names:
        ch = [r for r in champion.runs if r.slice == s]
        ca = [r for r in candidate.runs if r.slice == s]
        secondary.append(
            SecondaryRow(
                slice=s,
                distance_unit=next((r.distance_unit for r in ch + ca if r.distance_unit), ""),
                champion=_side_metrics(ch),
                candidate=_side_metrics(ca),
            )
        )
    nonzero = sum(1 for p in instances if p.rel_improvement)
    all_runs = champion.runs + candidate.runs
    labels, dlabels, versions = {}, {}, defaultdict(set)
    for run in all_runs:
        if run.error:
            continue
        labels.setdefault(run.source, run.labels)
        dlabels.setdefault(run.source, run.distance_label)
        versions[run.source].add(run.data_version)
    return Comparison(
        candidate=_side(candidate),
        champion=_side(champion),
        suite_name=champion.suite_name,
        split=champion.split,
        time_limit_s=champion.time_limit_s,
        num_instances=len(instances),
        statistics_settings=st,
        overall=_row("overall", instances, st),
        wilcoxon=stats.wilcoxon_test(
            [p.rel_improvement for p in instances if p.rel_improvement is not None]
        ),
        slices=slices,
        instances=instances,
        labels=labels,
        distance_labels=dlabels,
        data_versions={k: sorted(v) for k, v in versions.items()},
        secondary=secondary,
        min_p_two_sided=stats.min_p_two_sided(nonzero) if nonzero else None,
        workers=champion.workers,
    )


def statistics_settings() -> dict[str, Any]:
    s = suite_settings()
    st = dict(s["statistics"])
    st["slice_order"] = [*s["slices"]["solomon_classes"], *s["slices"]["amazon_cities"]]
    return st


def log_comparison(
    comparison: Comparison, name: str, context: dict[str, Any], title: str | None = None
) -> None:
    """Log the comparison and its report card on the active MLflow run."""
    from dmlab.harness.report_card import to_json, to_markdown

    card = to_json(comparison, context, title)
    prefix = f"{name}/" if name else ""
    mlflow.log_dict(card, f"{prefix}report_card.json")
    mlflow.log_text(to_markdown(card), f"{prefix}report_card.md")
    o, w = comparison.overall, comparison.wilcoxon
    key = f"{name}." if name else ""
    metrics = {
        f"{key}wilcoxon_p_greater": w.p_greater,
        f"{key}wilcoxon_p_less": w.p_less,
        f"{key}wilcoxon_p_two_sided": w.p_two_sided,
        f"{key}wins": o.wins,
        f"{key}losses": o.losses,
        f"{key}ties": o.ties,
        f"{key}excluded": o.excluded,
        f"{key}paired_instances": o.paired,
        f"{key}champion_reused_runs": comparison.champion.reused_runs,
    }
    for k in ("median_rel_improvement", "ci_low", "ci_high", "runtime_ratio"):
        v = getattr(o, k)
        if v is not None:
            metrics[f"{key}{k}"] = v
    mlflow.log_metrics(metrics)


def compare(
    candidate: SolverConfig,
    champion: SolverConfig,
    suite: Suite,
    runner: Runner,
    candidate_ref: str | None = None,
    champion_ref: str | None = None,
    reuse_champion: bool = True,
) -> tuple[Comparison, str]:
    """Run candidate and champion on the suite, compare, log. Returns (comparison, run id)."""
    configure_mlflow()
    mlflow.set_experiment(EXPERIMENT)
    git = git_info().model_dump()
    campaign = f"compare {candidate.key()} vs {champion.key()} {suite.name}/{suite.split}"
    tags = {
        "run_kind": "compare",
        "dmlab_module": MODULE,
        "suite": suite.name,
        "split": suite.split,
        "suite_fingerprint": suite.fingerprint(),
        "candidate": candidate.label(),
        "champion": champion.label(),
        "git_commit": git["commit"],
        "git_dirty": str(git["dirty"]).lower(),
    }
    with mlflow.start_run(run_name=f"compare {candidate.solver} vs {champion.solver}", tags=tags):
        run_id = mlflow.active_run().info.run_id
        mlflow.log_params(
            {
                "suite": suite.name,
                "split": suite.split,
                "seeds": ",".join(map(str, suite.seeds)),
                "time_limit_s": suite.time_limit_s,
                "num_instances": len(suite.refs),
                "workers": getattr(runner, "workers", "n/a"),
            }
        )
        if git["dirty"]:
            mlflow.log_text("\n".join(git["changed_files"]), "git_changed_files.txt")
        ev_champ, ev_cand = run_evaluations(
            [
                EvalSpec(
                    group="champion",
                    config=champion,
                    seeds=suite.seeds,
                    registry_ref=champion_ref,
                    reuse=reuse_champion,
                ),
                EvalSpec(
                    group="candidate",
                    config=candidate,
                    seeds=suite.seeds,
                    registry_ref=candidate_ref,
                ),
            ],
            suite,
            runner,
            campaign,
            git,
        )
        comparison = compare_evaluations(ev_cand, ev_champ, statistics_settings())
        log_comparison(comparison, "", run_context(git, run_id, runner))
    return comparison, run_id


def run_context(git: dict[str, Any], run_id: str, runner: Runner) -> dict[str, Any]:
    return {
        "mlflow_run_id": run_id,
        "mlflow_experiment": EXPERIMENT,
        "git_commit": git["commit"],
        "git_dirty": git["dirty"],
        "workers": getattr(runner, "workers", None),
    }


def log_named_comparison(
    comparison: Comparison,
    run_name: str,
    git: dict[str, Any],
    runner: Runner,
    tags: dict[str, str] | None = None,
    note: str | None = None,
) -> str:
    """Log a comparison's report card in its own nested run with a clear name."""
    with mlflow.start_run(run_name=run_name, nested=True, tags=tags or {}) as run:
        ctx = run_context(git, run.info.run_id, runner)
        if note:
            ctx["note"] = note
        log_comparison(comparison, "", ctx, title=run_name)
        return run.info.run_id
