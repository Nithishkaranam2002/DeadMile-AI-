"""One page report card for a comparison, as JSON and Markdown.

The JSON holds every number; the Markdown is rendered only from the JSON, so
the two can never disagree. Every number comes from the comparison, which
comes from MLflow logged runs. The card shows how the result compares with
the gates.yaml thresholds as information only; the promotion gate itself
(test split, human approval) comes in Module 4.
"""

from datetime import UTC, datetime
from typing import Any

from dmlab.harness.compare import Comparison
from dmlab.harness.gate_preview import RUNTIME_NOTE, preview

SIGNIFICANCE = 0.05  # used only for the plain words reading, not a gate
MIN_SLICE_CI = 3


def _pct(v: float | None, digits: int = 2) -> str:
    return "n/a" if v is None else f"{100 * v:+.{digits}f}%"


def _num(v: float | None, digits: int = 1) -> str:
    return "n/a" if v is None else f"{v:,.{digits}f}"


def _p(v: float) -> str:
    return f"{v:.2g}" if v < 0.001 else f"{v:.4f}"


def _short(version: str) -> str:
    return version.removeprefix("sha256:")[:12]


def _slice_ci(s: dict[str, Any]) -> str:
    # A bootstrap interval over fewer than 3 instances says nothing.
    if s["paired"] < MIN_SLICE_CI:
        return f"n/a (fewer than {MIN_SLICE_CI} instances)"
    return f"[{_pct(s['ci_low'])}, {_pct(s['ci_high'])}]"


def plain_words(c: Comparison) -> dict[str, str]:
    o, w = c.overall, c.wilcoxon
    cand, champ = c.candidate.label, c.champion.label
    excl = f", {o.excluded} not compared (see below)" if o.excluded else ""
    record = (
        f"The candidate ({cand}) planned a shorter total distance than the champion "
        f"({champ}) on {o.wins} of {o.instances} instances, a longer one on {o.losses}, "
        f"and the same on {o.ties}{excl}."
    )
    significant = w.p_two_sided < SIGNIFICANCE
    if significant and o.ci_low is not None and o.ci_low > 0:
        reading = "The candidate is better, and the difference is statistically significant."
    elif significant and o.ci_high is not None and o.ci_high < 0:
        reading = "The candidate is worse, and the difference is statistically significant."
    else:
        reading = "No statistically significant difference between candidate and champion."
    m = o.median_rel_improvement
    if m is None:
        size = "No instance could be compared, so there is no typical difference."
    elif m == 0:
        size = "On a typical (median) instance, both planned the same total distance."
    else:
        word = "shorter" if m > 0 else "longer"
        size = (
            f"On a typical (median) instance, the candidate's routes were {abs(100 * m):.2f}% "
            f"{word} in total distance than the champion's."
        )
    return {"record": record, "reading": reading, "size": size}


def fairness(c: Comparison) -> list[str]:
    notes = [
        f"Both sides used the same suite, the same {c.time_limit_s:g} s time limit and the "
        f"same number of workers ({c.workers}), with their solves interleaved on one pool.",
        f"Runtime gate: {RUNTIME_NOTE}.",
    ]
    for name, side in (("Champion", c.champion), ("Candidate", c.candidate)):
        if side.reused_runs:
            notes.append(
                f"{name}: {side.reused_runs} of {side.total_runs} solve runs were reused from "
                "earlier MLflow runs with the same config, git commit (clean tree), instance, "
                "seed, time limit, data version and worker count, instead of being run again. "
                "Reused runs ran at another time, under whatever else the machine was doing then."
            )
        else:
            notes.append(f"{name}: all {side.total_runs} solve runs ran fresh for this comparison.")
    return notes


def to_json(c: Comparison, context: dict[str, Any], title: str | None = None) -> dict[str, Any]:
    return {
        "report_card_version": 2,
        "title": title or f"Report card: {c.candidate.label} vs champion {c.champion.label}",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "kind": "routing comparison",
        "provenance": context,
        "plain_words": plain_words(c),
        "seed_policy": {
            "rule": (
                "Seeded solvers run every seed of the suite and are averaged per instance. "
                "Solvers without a seed (OR Tools, nearest neighbor) run once per instance."
            ),
            "candidate": c.candidate.seed_policy,
            "champion": c.champion.seed_policy,
        },
        "sign_convention": (
            "relative improvement r = (champion - candidate) / champion per instance, "
            "seeds averaged first; r > 0 means the candidate is better (shorter)"
        ),
        "primary_metric": "total distance (the only metric used for pass or fail)",
        "gate_preview": {
            "note": "information only, not a promotion decision (the promotion gate, on the "
            "test split with human approval, comes in Module 4)",
            "checks": [g.model_dump() for g in preview(c)],
        },
        "fairness": fairness(c),
        "comparison": c.model_dump(),
    }


def to_markdown(card: dict[str, Any]) -> str:
    c = card["comparison"]
    o, w, st = c["overall"], c["wilcoxon"], c["statistics_settings"]
    pw = card["plain_words"]
    level = int(round(100 * st["ci_level"]))
    lines = [
        f"# {card['title']}",
        "",
        f"Suite **{c['suite_name']}** on the **{c['split']}** split: {c['num_instances']} "
        f"instances, {c['time_limit_s']:g} s time limit per run. Generated "
        f"{card['generated_at']} from MLflow run `{card['provenance'].get('mlflow_run_id')}` "
        f"(experiment `{card['provenance'].get('mlflow_experiment')}`), git commit "
        f"`{str(card['provenance'].get('git_commit'))[:10]}`"
        + (" (uncommitted changes)" if card["provenance"].get("git_dirty") else "")
        + ".",
        "",
        *([f"> {card['provenance']['note']}", ""] if card["provenance"].get("note") else []),
        "## In plain words",
        "",
        f"* {pw['record']}",
        f"* {pw['reading']}",
        f"* {pw['size']}",
        "",
        "## Statistics",
        "",
        "| | Value |",
        "|---|---|",
        f"| Instances compared (both feasible on every run) | {o['paired']} of {o['instances']} |",
        f"| Wins / losses / ties for the candidate | {o['wins']} / {o['losses']} / {o['ties']} |",
        f"| Median relative improvement (r > 0 = candidate better) | "
        f"{_pct(o['median_rel_improvement'], 3)} |",
        f"| Bootstrap {level}% CI of the median | [{_pct(o['ci_low'], 3)}, "
        f"{_pct(o['ci_high'], 3)}] |",
        f"| Wilcoxon signed rank p, two sided (used by the gates) | {_p(w['p_two_sided'])} |",
        f"| Wilcoxon p, one sided (candidate better) | {_p(w['p_greater'])} |",
        f"| Wilcoxon p, one sided (candidate worse) | {_p(w['p_less'])} |",
        f"| Wilcoxon test used | {w['method']}, {w['n_nonzero']} non-tied instances |",
        f"| Smallest two sided p reachable with {w['n_nonzero']} non-tied instances | "
        + ("n/a" if c["min_p_two_sided"] is None else _p(c["min_p_two_sided"]))
        + " |",
        f"| Runtime ratio (candidate / champion, seed averaged) | {_num(o['runtime_ratio'], 2)} |",
        f"| Candidate feasible instances | {o['candidate_feasible_instances']} of "
        f"{o['instances']} |",
        f"| Champion feasible instances | {o['champion_feasible_instances']} of {o['instances']} |",
        "",
        f"Sign convention: {card['sign_convention']}. Bootstrap: {st['bootstrap_resamples']:,} "
        f"resamples of instances, seed {st['bootstrap_seed']}, percentile interval. "
        f"Primary metric: {card['primary_metric']}.",
        "",
        "## Gate thresholds (information only)",
        "",
        f"Not a promotion decision: {card['gate_preview']['note']}. Thresholds from "
        "configs/gates.yaml.",
        "",
        "| Gate | Threshold | Observed | Met |",
        "|---|---|---|---|",
    ]
    for g in card["gate_preview"]["checks"]:
        note = f" ({g['note']})" if g["note"] else ""
        lines.append(
            f"| {g['gate']} | {g['rule']} | {g['observed']}{note} | {'yes' if g['met'] else 'no'} |"
        )
    lines += [
        "",
        "## Fair runs",
        "",
        *[f"* {n}" for n in card["fairness"]],
        "",
        "## Seeds",
        "",
        f"* Rule: {card['seed_policy']['rule']}",
        f"* Candidate: {card['seed_policy']['candidate']}.",
        f"* Champion: {card['seed_policy']['champion']}.",
        "",
        "## Per slice",
        "",
        "| Slice | Instances | W / L / T | Median r | "
        f"{level}% CI | Champion mean distance | Candidate mean distance | Unit | "
        "Runtime ratio | Feasible cand / champ |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in c["slices"]:
        lines.append(
            f"| {s['slice']} | {s['instances']} | {s['wins']} / {s['losses']} / {s['ties']} | "
            f"{_pct(s['median_rel_improvement'])} | {_slice_ci(s)} "
            f"| {_num(s['champion_mean_distance'])} | {_num(s['candidate_mean_distance'])} | "
            f"{s['distance_unit']} | {_num(s['runtime_ratio'], 2)} | "
            f"{s['candidate_feasible_instances']} / {s['champion_feasible_instances']} |"
        )
    lines += [
        "",
        "Slices are small (a few instances each), so slice CIs are wide; read them as "
        "direction, not proof.",
        "",
        "## Other metrics (information only, not used for pass or fail)",
        "",
        "Means over instances of seed averaged values, champion / candidate.",
        "",
        "| Slice | Vehicles used | Distance per stop | Productivity | Time window violations "
        "| Cost per stop |",
        "|---|---|---|---|---|---|",
    ]
    cost_notes = set()
    for row in c["secondary"]:
        ch, ca = row["champion"], row["candidate"]
        prod = ch["productivity_name"] or ca["productivity_name"] or "productivity"
        cost_notes |= {x for x in (ch["cost_note"], ca["cost_note"]) if x}
        lines.append(
            f"| {row['slice']} | {_num(ch['vehicles_used'], 2)} / {_num(ca['vehicles_used'], 2)} "
            f"| {_num(ch['distance_per_stop'], 2)} / {_num(ca['distance_per_stop'], 2)} "
            f"{row['distance_unit']} | {_num(ch['productivity'], 2)} / "
            f"{_num(ca['productivity'], 2)} {prod.replace('_', ' ')} | "
            f"{_num(ch['time_window_violations'], 2)} / {_num(ca['time_window_violations'], 2)} "
            f"| {_num(ch['cost_per_stop'], 2)} / {_num(ca['cost_per_stop'], 2)} |"
        )
    lines += [
        "",
        "Solomon time is in abstract units, so its productivity is stops per 100 time units, "
        "not per driver hour. Cost per stop: " + ("; ".join(sorted(cost_notes)) or "n/a") + ".",
        "",
        "## What the numbers are",
        "",
    ]
    for source, label in c["distance_labels"].items():
        extra = [x for x in c["labels"].get(source, []) if x not in label]
        lines.append(f"* **{source}**: " + "; ".join([label, *extra]) + ".")
    for source, versions in c["data_versions"].items():
        lines.append(
            f"* {source} data version(s): " + ", ".join(f"`{_short(v)}`" for v in versions)
        )
    excluded = [i for i in c["instances"] if i["outcome"] == "excluded"]
    lines += ["", "## Not compared", ""]
    lines += [f"* {i['instance']} ({i['slice']}): {i['note']}" for i in excluded] or [
        "* None: both solvers were feasible on every run of every instance."
    ]
    lines += [
        "",
        "<details><summary>Per instance results</summary>",
        "",
        "| Instance | Slice | Champion distance | Candidate distance | r | Outcome |",
        "|---|---|---|---|---|---|",
    ]
    for i in c["instances"]:
        lines.append(
            f"| {i['instance']} | {i['slice']} | {_num(i['champion_distance'])} | "
            f"{_num(i['candidate_distance'])} | {_pct(i['rel_improvement'], 3)} | "
            f"{i['outcome']} |"
        )
    lines += ["", "</details>", ""]
    return "\n".join(lines)
