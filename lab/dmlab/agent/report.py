"""Cycle report (JSON and Markdown), logged on the cycle's parent MLflow run.

Every number comes from the cycle's logged runs (each variant row names its
MLflow run). Relative improvements are unitless: r = (champion - candidate) /
champion per instance, seeds averaged first, so r > 0 means shorter distance.
"""

from datetime import UTC, datetime
from typing import Any

from dmlab.agent.state import CycleState, EvalSummary, VariantRecord

STATUS_ORDER = {
    "nominated": 0,
    "confirmed": 1,
    "not_confirmed": 2,
    "promising": 3,
    "not_better": 4,
    "infeasible": 5,
    "crashed": 6,
    "rejected": 7,
    "pending": 8,
}
LABELS = [
    "Solomon distances are abstract benchmark units, not miles.",
    "Amazon distances are haversine km on stop coordinates (Amazon Last Mile 2021 data).",
    "Relative improvements are unitless; r > 0 means the variant is shorter than the champion.",
    "Quick suite = tune split subset (screening); full suite = validation split (confirmation). "
    "The test split is used only by the promotion gate (Module 4) and never seen here.",
]


def ranked(variants: list[VariantRecord]) -> list[VariantRecord]:
    def key(v: VariantRecord) -> tuple[int, float, str]:
        m = v.full.median_rel_improvement if v.full else None
        if m is None and v.quick:
            m = v.quick.median_rel_improvement
        return (STATUS_ORDER[v.status], -(m if m is not None else float("-inf")), v.vid)

    return sorted(variants, key=key)


def _eval(e: EvalSummary | None) -> dict[str, Any] | None:
    if e is None:
        return None
    return e.model_dump()


def build(state: CycleState, extra: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for rank, v in enumerate(ranked(state.variants), start=1):
        rows.append(
            {
                "rank": rank,
                "vid": v.vid,
                "round": v.round,
                "name": v.name,
                "kind": v.kind,
                "status": v.status,
                "reason": v.reason,
                "hypothesis": v.hypothesis,
                "config": v.config_label,
                "config_key": v.config_key,
                "quick": _eval(v.quick),
                "full": _eval(v.full),
                "lesson": v.lesson,
                "mlflow_run_id": v.run_id,
                "llm_share": v.llm_share,
            }
        )
    rejected = [v for v in state.variants if v.status == "rejected"]
    return {
        "title": f"Experiment agent cycle {state.cycle_id}",
        "created_at": datetime.now(UTC).isoformat(),
        "cycle_id": state.cycle_id,
        "session": state.session,
        "model": {
            "name": state.model,
            "offline": state.offline,
            "note": "offline backup model (Ollama, local)" if state.offline else "main cloud model",
        },
        "champion": state.champion,
        "quick_only": state.quick_only,
        "confirm_top": state.confirm_top,
        "rounds": state.round,
        "stop_reason": state.stop_reason,
        "end_reason": state.end_reason,
        "budgets": state.budgets,
        "variants_proposed": len(state.variants),
        "variants_rejected": len(rejected),
        "ranked": rows,
        "nominee": state.nominee,
        "nomination_note": state.nomination_note,
        "champion_baseline_runs": {
            "quick": state.champion_quick_run,
            "full": state.champion_full_run,
        },
        "llm_calls": state.llm_calls,
        "labels": LABELS,
        **extra,
    }


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{100 * v:+.3f}%"


def _ci(e: dict[str, Any] | None) -> str:
    if not e:
        return ""
    return f"[{_pct(e['ci_low'])}, {_pct(e['ci_high'])}]"


def _brief(e: dict[str, Any] | None) -> str:
    if not e:
        return "not run"
    p = "n/a" if e["p_two_sided"] is None else f"{e['p_two_sided']:.3g}"
    return (
        f"{_pct(e['median_rel_improvement'])} {_ci(e)}, p={p}, "
        f"W/L/T {e['wins']}/{e['losses']}/{e['ties']}, "
        f"feasible runs {e['candidate_feasible_runs']}/{e['candidate_runs']}"
    )


def to_markdown(r: dict[str, Any]) -> str:
    b = r["budgets"]
    used, lim = b.get("used", {}), b.get("limits", {})
    nominee = r["nominee"]
    q, f = r["suite_settings"]["quick"], r["suite_settings"]["full"]
    lines = [
        f"# {r['title']}",
        "",
        f"* Model: **{r['model']['name']}** ({r['model']['note']})",
        f"* Session: {r['session']}; git commit {r.get('git_commit', '?')[:10]}"
        f"{' (dirty tree)' if r.get('git_dirty') else ''}",
        f"* Champion: {r['champion'].get('ref')}: {r['champion'].get('label')}",
        f"* Screening: quick suite on the **{q['split']}** split ({q['instances']} instances, "
        f"seeds {q['seeds']}, {q['time_limit_s']:g} s per run)",
        f"* Confirmation: full suite on the **{f['split']}** split ({f['instances']} instances, "
        f"seeds {f['seeds']}, {f['time_limit_s']:g} s per run): "
        + ("skipped (quick phase only)" if r["quick_only"] else f"top {r['confirm_top']}"),
        f"* Rounds: {r['rounds']}; variants proposed: {r['variants_proposed']}, "
        f"rejected before running: {r['variants_rejected']}",
        f"* Stop reason: {r['stop_reason'] or 'none (no budget was hit)'}",
        f"* End of proposing: {r['end_reason'] or 'n/a'}",
        "",
        "## Outcome",
        "",
        (
            f"Nominated **{nominee['vid']} {nominee['name']}** as @challenger "
            f"(routing-solver v{nominee['version']}): {nominee['config']}. "
            "Moving @champion still needs the promotion gate and human approval (Module 4)."
            if nominee
            else f"**No challenger nominated.** {r['nomination_note']}"
        ),
        "",
        "## Ranked variants",
        "",
        "| # | id | kind | name | status | quick (tune) | full (validation) | reason |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in r["ranked"]:
        reason = row["reason"].replace("|", "/").replace("\n", " ")
        lines.append(
            f"| {row['rank']} | {row['vid']} | {row['kind'] or '?'} | {row['name'] or '?'} | "
            f"{row['status']} | {_brief(row['quick']) if row['quick'] else ''} | "
            f"{_brief(row['full']) if row['full'] else ''} | {reason} |"
        )
    lines += ["", "## Lessons", ""]
    for row in r["ranked"]:
        if row["lesson"]:
            lines.append(f"* {row['vid']} {row['name']}: {row['lesson']}")
    lines += [
        "",
        "## Budgets (rules, not results)",
        "",
        f"* Variants: {used.get('variants_proposed')} of {lim.get('max_variants')}",
        f"* CPU: {used.get('cpu_minutes')} of {lim.get('max_cpu_minutes')} min",
        f"* LLM this cycle: {used.get('cycle_llm_tokens')} tokens, "
        f"${used.get('cycle_llm_usd', 0):.4f}",
        f"* LLM this session: {used.get('session_llm_tokens')} of {lim.get('llm_max_tokens')} "
        f"tokens, ${used.get('session_llm_usd', 0):.4f} of ${lim.get('llm_max_usd', 0):.2f}",
        f"* Per run wall clock: {lim.get('wall_clock_seconds')} s",
        f"* Budget file: {b.get('source')}",
        "",
        "## LLM calls",
        "",
        "| # | node | model | prompt tokens | completion tokens | cost (USD) | artifacts |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in r["llm_calls"]:
        lines.append(
            f"| {c['index']} | {c['node']} | {c['model']} | {c['prompt_tokens']} | "
            f"{c['completion_tokens']} | {c['cost_usd']:.5f} | {c['artifact']} |"
        )
    lines += ["", "## Labels", ""] + [f"* {x}" for x in r["labels"]]
    return "\n".join(lines) + "\n"
