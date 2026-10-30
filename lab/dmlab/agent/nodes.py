"""Nodes of the experiment agent graph.

Each node takes the state and the run context and returns a state update.
Budgets are checked before every LLM call and every solve batch; when one is
hit the node sets ``stop_reason`` and the graph goes straight to ``finalize``.
"""

import json
from contextlib import contextmanager
from typing import Any

import mlflow
from langgraph.runtime import Runtime
from mlflow import MlflowClient
from pydantic import BaseModel, ValidationError

from dmlab.agent import prompts, report
from dmlab.agent.evaluate import (
    estimate_cpu_seconds,
    evaluate_candidate,
    evaluate_champion,
    fresh_cpu_seconds,
)
from dmlab.agent.llm import LLMCall, LLMError, parse_json, redact
from dmlab.agent.state import CycleContext, CycleState, VariantRecord
from dmlab.agent.variants import (
    VARIANT_ADAPTER,
    CodeVariant,
    ProposalBatch,
    mentions_time_limit,
    to_solver_config,
)
from dmlab.harness import registry
from dmlab.harness.runners import SolverConfig

MAX_OUTPUT_TOKENS = {"hypothesize": 4000, "propose": 8000, "reflect": 4000}
MODULE = "3"


def _ctx(runtime: Runtime[CycleContext]) -> CycleContext:
    return runtime.context


def _copy(state: CycleState) -> list[VariantRecord]:
    return [v.model_copy(deep=True) for v in state.variants]


def _suites(ctx: CycleContext) -> dict[str, Any]:
    def info(s: Any) -> dict[str, Any]:
        return {
            "name": s.name,
            "split": s.split,
            "instances": len(s.refs),
            "seeds": s.seeds,
            "time_limit_s": s.time_limit_s,
        }

    return {"quick (screening)": info(ctx.quick_suite), "full (confirmation)": info(ctx.full_suite)}


@contextmanager
def child_run(ctx: CycleContext, name: str, tags: dict[str, str], parent: str | None = None):
    """A nested MLflow run under the cycle (or under ``parent``)."""
    mlflow.set_experiment(experiment_id=ctx.experiment_id)
    base = {
        "dmlab_module": MODULE,
        "git_commit": ctx.git["commit"],
        "git_dirty": str(ctx.git["dirty"]).lower(),
    }
    with mlflow.start_run(
        run_name=name,
        experiment_id=ctx.experiment_id,
        parent_run_id=parent or ctx.cycle_run_id,
        nested=True,
        tags=base | tags,
    ) as run:
        yield run


def _call_llm(
    state: CycleState,
    ctx: CycleContext,
    node: str,
    messages: list[dict[str, str]],
    schema: type[BaseModel],
) -> tuple[LLMCall | None, str | None]:
    """Budget check, call, log prompt and response. Returns (call, stop_reason)."""
    max_out = MAX_OUTPUT_TOKENS[node]
    worst_tokens, worst_usd = ctx.llm.worst_case(ctx.llm.prepare(messages, schema), max_out)
    refusal = ctx.budget.llm_refusal(worst_tokens, worst_usd)
    if refusal:
        return None, f"{refusal} (before {node})"
    try:
        call = ctx.llm.complete(node, messages, schema, max_out)
    except LLMError as exc:
        return None, f"LLM call failed at {node}: {exc}"
    ctx.budget.add_llm(call.prompt_tokens + call.completion_tokens, call.cost_usd)
    client = MlflowClient()
    # Logged after every call, so a later cycle of the session can sum usage
    # even if this one crashes.
    client.log_metric(
        ctx.cycle_run_id, "llm_tokens_total", ctx.budget.cycle_tokens, step=call.index
    )
    client.log_metric(ctx.cycle_run_id, "llm_cost_usd", ctx.budget.cycle_usd, step=call.index)
    base = f"llm/{call.index:02d}_{node}"
    prompt_md = "\n\n".join(f"### {m['role']}\n\n{m['content']}" for m in call.messages)
    client.log_text(ctx.cycle_run_id, prompt_md, f"{base}_prompt.md")
    client.log_dict(ctx.cycle_run_id, call.model_dump(), f"{base}_call.json")
    ctx.say(
        f"  LLM {node}: {call.prompt_tokens}+{call.completion_tokens} tokens, "
        f"${call.cost_usd:.4f}, {call.latency_s:.1f}s ({call.model})"
    )
    state.llm_calls.append(
        {
            "index": call.index,
            "node": node,
            "model": call.model,
            "prompt_tokens": call.prompt_tokens,
            "completion_tokens": call.completion_tokens,
            "reasoning_tokens": call.reasoning_tokens,
            "cost_usd": call.cost_usd,
            "cost_note": call.cost_note,
            "latency_s": round(call.latency_s, 2),
            "artifact": f"{base}_call.json",
        }
    )
    return call, None


def _parse(call: LLMCall, schema: type[BaseModel]) -> tuple[Any, str | None]:
    try:
        raw = parse_json(call.response_text)
    except (json.JSONDecodeError, ValueError) as exc:
        return None, f"reply is not valid JSON ({exc})"
    try:
        return schema.model_validate(raw), None
    except ValidationError as exc:
        return raw, _errors(exc)


def _errors(exc: ValidationError, limit: int = 3) -> str:
    errs = exc.errors()
    parts = [f"{'.'.join(map(str, e['loc'])) or '(root)'}: {e['msg']}" for e in errs[:limit]]
    more = f" (+{len(errs) - limit} more)" if len(errs) > limit else ""
    return "schema validation failed: " + "; ".join(parts) + more


def _memory_view(entry: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "name",
        "kind",
        "hypothesis",
        "variant",
        "status",
        "reason",
        "quick_median",
        "full_median",
        "lesson",
        "champion_version",
        "similarity",
    )
    out = {k: entry.get(k) for k in keep if entry.get(k) is not None}
    if isinstance(out.get("variant"), dict):
        out["variant"] = {
            k: v for k, v in out["variant"].items() if k not in ("rationale", "hypothesis")
        }
    return out


# Nodes -------------------------------------------------------------------


def load_context(state: CycleState, runtime: Runtime[CycleContext]) -> dict[str, Any]:
    """Load the champion, budgets and similar past experiments from memory."""
    ctx = _ctx(runtime)
    query = f"experiments against champion {state.champion.get('label')} to reduce total distance"
    found = ctx.memory.similar(query, limit=8)
    ctx.say(f"Memory: {ctx.memory.count()} past experiments stored, {len(found)} retrieved")
    return {"memory_context": [_memory_view(e) for e in found], "budgets": ctx.budget.snapshot()}


def hypothesize(state: CycleState, runtime: Runtime[CycleContext]) -> dict[str, Any]:
    """Ask the LLM for hypotheses for this round."""
    ctx = _ctx(runtime)
    rnd = state.round + 1
    ctx.say(f"Round {rnd}: hypothesize")
    n = min(state.per_round, ctx.budget.variant_slots_left())
    text = prompts.context_block(state, _suites(ctx), ctx.budget.snapshot())
    call, stop = _call_llm(
        state, ctx, "hypothesize", prompts.hypothesize_messages(text, n), prompts.HypothesisSet
    )
    update: dict[str, Any] = {
        "round": rnd,
        "llm_calls": state.llm_calls,
        "budgets": ctx.budget.snapshot(),
    }
    if stop:
        return update | {"stop_reason": stop}
    parsed, err = _parse(call, prompts.HypothesisSet)
    if err:
        return update | {
            "stop_reason": f"invalid LLM reply at hypothesize ({err}); logged as "
            f"{state.llm_calls[-1]['artifact']}"
        }
    return update | {"hypotheses": [h.model_dump() for h in parsed.hypotheses]}


def propose(state: CycleState, runtime: Runtime[CycleContext]) -> dict[str, Any]:
    """Ask the LLM for variants, then screen every proposal."""
    ctx = _ctx(runtime)
    n = min(state.per_round, ctx.budget.variant_slots_left())
    similar: dict[str, dict[str, Any]] = {}
    for h in state.hypotheses:
        for e in ctx.memory.similar(h["statement"], limit=3):
            similar.setdefault(str(e.get("config_key")) + str(e.get("champion_key")), e)
    text = prompts.context_block(state, _suites(ctx), ctx.budget.snapshot())
    msgs = prompts.propose_messages(
        text, state.hypotheses, n, [_memory_view(e) for e in similar.values()]
    )
    call, stop = _call_llm(state, ctx, "propose", msgs, ProposalBatch)
    update: dict[str, Any] = {"llm_calls": state.llm_calls, "budgets": ctx.budget.snapshot()}
    if stop:
        return update | {"stop_reason": stop}
    variants = _copy(state)
    pending: list[str] = []

    def next_vid() -> str:
        return f"v{len(variants) + 1:02d}"

    try:
        raw = parse_json(call.response_text)
    except (json.JSONDecodeError, ValueError) as exc:
        raw, items = call.response_text, None
        reply_error = f"reply is not valid JSON ({exc})"
    else:
        items = raw.get("variants") if isinstance(raw, dict) else None
        reply_error = None if isinstance(items, list) else "reply has no 'variants' list"
    if reply_error:
        ctx.budget.variants_proposed += 1
        variants.append(
            VariantRecord(
                vid=next_vid(),
                round=state.round,
                status="rejected",
                reason=f"invalid proposal reply: {reply_error}",
                raw=redact(str(raw))[:2000],
                proposed_by_call=call.index,
            )
        )
        ctx.say(f"  {variants[-1].vid} rejected: {variants[-1].reason}")
        return update | {"variants": variants, "pending": []}

    share = {
        "prompt_tokens": call.prompt_tokens / max(1, len(items)),
        "completion_tokens": call.completion_tokens / max(1, len(items)),
        "cost_usd": call.cost_usd / max(1, len(items)),
    }
    champion = SolverConfig(**state.champion["config"])
    keys_this_cycle = {v.config_key for v in variants if v.config_key and v.status != "rejected"}
    for item in items:
        rec = VariantRecord(
            vid=next_vid(),
            round=state.round,
            status="rejected",
            reason="",
            raw=item,
            proposed_by_call=call.index,
            llm_share=share,
        )
        if isinstance(item, dict):
            rec.name = str(item.get("name", ""))[:80]
            rec.kind = str(item.get("kind")) if item.get("kind") else None
            rec.hypothesis = str(item.get("hypothesis", ""))[:600]
        ctx.budget.variants_proposed += 1
        rec.reason = _screen(rec, item, champion, state, ctx, keys_this_cycle)
        if not rec.reason:
            rec.status = "pending"
            rec.reason = "passed screening"
            keys_this_cycle.add(rec.config_key)
            pending.append(rec.vid)
            ctx.say(f"  {rec.vid} accepted: {rec.name} ({rec.config_label})")
        else:
            ctx.say(f"  {rec.vid} rejected: {rec.reason}")
        variants.append(rec)
    return update | {"variants": variants, "pending": pending}


def _screen(
    rec: VariantRecord,
    item: Any,
    champion: SolverConfig,
    state: CycleState,
    ctx: CycleContext,
    keys_this_cycle: set[str | None],
) -> str:
    """Empty string when the proposal may run, else the rejection reason."""
    if ctx.budget.variants_proposed > ctx.budget.limits.max_variants:
        return f"over the per cycle variant cap ({ctx.budget.limits.max_variants})"
    if mentions_time_limit(item):
        return "tries to set a time limit; the time limit is fixed by the suite"
    try:
        variant = VARIANT_ADAPTER.validate_python(item)
    except ValidationError as exc:
        return _errors(exc)
    rec.variant = variant.model_dump(mode="json")
    rec.kind, rec.name, rec.hypothesis = variant.kind, variant.name, variant.hypothesis
    if isinstance(variant, CodeVariant):
        return "code variants are disabled until Module 4 adds the sandbox"
    try:
        config = to_solver_config(variant, champion)
    except ValueError as exc:
        return f"not a valid solver config: {exc}"
    rec.config = config.model_dump()
    rec.config_key, rec.config_label = config.key(), config.label()
    if config.key() == champion.key():
        return "identical to the champion config"
    if config.key() in keys_this_cycle:
        return "duplicate of another variant in this cycle"
    earlier = ctx.memory.find_config(config.key(), state.champion["key"])
    if earlier:
        e = earlier[0]
        m = e.get("quick_median")
        res = f", quick median {100 * m:+.2f}%" if isinstance(m, float) else ""
        cycle, status = e.get("cycle_id"), e.get("status")
        return f"already tested against this champion in cycle {cycle} ({status}{res})"
    return ""


def run_quick(state: CycleState, runtime: Runtime[CycleContext]) -> dict[str, Any]:
    """Run accepted variants on the quick suite, each in its own child run."""
    ctx = _ctx(runtime)
    variants = _copy(state)
    suite = ctx.quick_suite
    champion = SolverConfig(**state.champion["config"])
    update: dict[str, Any] = {}
    wall = ctx.budget.limits.wall_clock_seconds
    for vid in state.pending:
        rec = next(v for v in variants if v.vid == vid)
        config = SolverConfig(**rec.config)
        estimate = estimate_cpu_seconds(config, suite)
        if "quick" not in ctx.champion_evals:
            estimate += estimate_cpu_seconds(champion, suite)
        refusal = ctx.budget.cpu_refusal(estimate, f"quick run of {vid}")
        if refusal:
            rec.status, rec.reason = "rejected", f"not run: {refusal}"
            update["stop_reason"] = refusal
            ctx.say(f"  {vid} not run: {refusal}")
            break
        if "quick" not in ctx.champion_evals:
            with child_run(
                ctx,
                f"champion baseline quick ({suite.split})",
                {"run_kind": "agent_champion_baseline", "suite": suite.name},
            ) as run:
                ev = evaluate_champion(champion, suite, ctx.runner, ctx.git, ctx.champion_ref)
                ctx.budget.add_cpu(fresh_cpu_seconds(ev, wall))
                ctx.champion_evals["quick"] = ev
                update["champion_quick_run"] = run.info.run_id
        tags = {
            "run_kind": "agent_variant",
            "variant_id": vid,
            "variant_kind": rec.kind or "",
            "config_key": rec.config_key or "",
            "agent_session": state.session,
            "agent_cycle": state.cycle_id,
            "llm_model": state.model,
        }
        ctx.say(f"  {vid} quick run: {rec.config_label}")
        with child_run(ctx, f"{vid} {rec.name}"[:250], tags) as run:
            rec.run_id = run.info.run_id
            mlflow.log_dict(
                {"variant": rec.variant, "raw_proposal": rec.raw, "solver_config": rec.config},
                "variant.json",
            )
            mlflow.log_params(
                {
                    "variant_id": vid,
                    "kind": rec.kind,
                    "config": rec.config_label[:500],
                    "suite": suite.name,
                    "split": suite.split,
                    "time_limit_s": suite.time_limit_s,
                    "seeds": ",".join(map(str, suite.seeds)),
                }
            )
            mlflow.log_metrics({f"llm_share_{k}": v for k, v in rec.llm_share.items()})
            mlflow.set_tag(
                "llm_share_note",
                "equal share of the proposing LLM call "
                f"(call {rec.proposed_by_call}); exact per call usage is on the cycle run",
            )
            summary, _ = evaluate_candidate(
                config,
                ctx.champion_evals["quick"],
                suite,
                ctx.runner,
                ctx.git,
                run.info.run_id,
                wall,
                with_gate_checks=False,
            )
            rec.quick = summary
            ctx.budget.add_cpu(summary.cpu_seconds)
            mlflow.log_metrics(_summary_metrics("quick", summary))
        if summary.wall_clock_exceeded:
            update["stop_reason"] = (
                f"per run wall clock budget ({wall:g} s) exceeded while running {vid}"
            )
            break
    if update.get("stop_reason"):
        for rec in variants:
            if rec.status == "pending" and rec.quick is None and rec.vid in state.pending:
                rec.status = "rejected"
                rec.reason = (
                    rec.reason
                    if rec.reason.startswith("not run")
                    else (f"not run: the cycle stopped ({update['stop_reason']})")
                )
    return update | {"variants": variants, "budgets": ctx.budget.snapshot()}


def _summary_metrics(prefix: str, s: Any) -> dict[str, float]:
    out = {
        f"{prefix}.candidate_feasible_runs": s.candidate_feasible_runs,
        f"{prefix}.candidate_runs": s.candidate_runs,
        f"{prefix}.wins": s.wins,
        f"{prefix}.losses": s.losses,
        f"{prefix}.ties": s.ties,
        f"{prefix}.cpu_seconds": s.cpu_seconds,
    }
    for k in ("median_rel_improvement", "ci_low", "ci_high", "p_two_sided", "runtime_ratio"):
        v = getattr(s, k)
        if v is not None:
            out[f"{prefix}.{k}"] = v
    return out


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{100 * v:+.3f}%"


def evaluate(state: CycleState, runtime: Runtime[CycleContext]) -> dict[str, Any]:
    """Classify the quick results of this round."""
    ctx = _ctx(runtime)
    variants = _copy(state)
    client = MlflowClient()
    for vid in state.pending:
        rec = next(v for v in variants if v.vid == vid)
        q = rec.quick
        if q is None:
            continue  # not run (budget); already marked rejected
        if q.errors:
            rec.status = "crashed"
            rec.reason = f"{len(q.errors)} distinct run errors, first: {q.errors[0][:200]}"
        elif q.candidate_feasible_runs < q.candidate_runs:
            rec.status = "infeasible"
            rec.reason = (
                f"infeasible on {q.candidate_runs - q.candidate_feasible_runs} of "
                f"{q.candidate_runs} quick runs (checked on the original instances)"
            )
        elif q.median_rel_improvement is None:
            rec.status, rec.reason = "infeasible", "no instance could be paired with the champion"
        elif q.median_rel_improvement <= 0:
            rec.status = "not_better"
            rec.reason = (
                f"quick median {_pct(q.median_rel_improvement)} "
                f"[{_pct(q.ci_low)}, {_pct(q.ci_high)}]: not better than the champion"
            )
        else:
            rec.status = "promising"
            p = "n/a" if q.p_two_sided is None else f"{q.p_two_sided:.3g}"
            rec.reason = (
                f"quick median {_pct(q.median_rel_improvement)} "
                f"[{_pct(q.ci_low)}, {_pct(q.ci_high)}], p={p}, "
                f"W/L/T {q.wins}/{q.losses}/{q.ties}, feasible on every run"
            )
        ctx.say(f"  {vid} {rec.status}: {rec.reason}")
        if rec.run_id:
            client.set_tag(rec.run_id, "status", rec.status)
            client.set_tag(rec.run_id, "status_reason", rec.reason[:5000])
    return {"variants": variants, "pending": []}


def reflect(state: CycleState, runtime: Runtime[CycleContext]) -> dict[str, Any]:
    """Ask the LLM for a lesson per variant, store memory, decide whether to go on."""
    ctx = _ctx(runtime)
    variants = _copy(state)
    this_round = [v for v in variants if v.round == state.round]
    slots = ctx.budget.variant_slots_left()
    can_continue = slots > 0 and state.round < state.max_rounds
    update: dict[str, Any] = {}
    reflection = None
    if this_round and not state.stop_reason:
        text = prompts.context_block(
            state.model_copy(update={"variants": variants}), _suites(ctx), ctx.budget.snapshot()
        )
        call, stop = _call_llm(
            state,
            ctx,
            "reflect",
            prompts.reflect_messages(text, [v.vid for v in this_round], can_continue),
            prompts.Reflection,
        )
        if stop:
            update["stop_reason"] = stop
        else:
            reflection, err = _parse(call, prompts.Reflection)
            if err:
                reflection = None
                ctx.say(f"  reflection reply rejected: {err}")
                update["keep_going_reason"] = f"reflection reply invalid ({err}); stopping rounds"
    lessons = {x.vid: x.lesson for x in reflection.lessons} if reflection else {}
    for v in this_round:
        v.lesson = lessons.get(v.vid)
        if v.variant is None or v.reason.startswith(("already tested", "not run")):
            continue  # nothing new to remember (a variant that never ran has no result)
        v.memory_id = ctx.memory.store(_memory_entry(v, state))
    keep = bool(reflection and reflection.continue_search and can_continue)
    if not keep and not update.get("stop_reason") and not state.stop_reason:
        if slots <= 0:
            end = f"variant cap reached ({ctx.budget.limits.max_variants} proposals)"
        elif state.round >= state.max_rounds:
            end = f"round limit reached ({state.max_rounds})"
        elif reflection is not None:
            end = f"the agent chose to stop: {reflection.reason}"
        else:
            end = update.get("keep_going_reason", "no reflection")
        update["end_reason"] = end
    return update | {
        "variants": variants,
        "keep_going": keep,
        "llm_calls": state.llm_calls,
        "budgets": ctx.budget.snapshot(),
    }


def _memory_entry(v: VariantRecord, state: CycleState) -> dict[str, Any]:
    return {
        "vid": v.vid,
        "cycle_id": state.cycle_id,
        "session": state.session,
        "llm_model": state.model,
        "champion_version": state.champion.get("version"),
        "champion_key": state.champion["key"],
        "name": v.name,
        "kind": v.kind,
        "hypothesis": v.hypothesis,
        "variant": v.variant,
        "config_key": v.config_key,
        "config_label": v.config_label,
        "status": v.status,
        "reason": v.reason,
        "quick_median": v.quick.median_rel_improvement if v.quick else None,
        "quick_ci": [v.quick.ci_low, v.quick.ci_high] if v.quick else None,
        "quick_suite": "quick/tune",
        "lesson": v.lesson,
        "mlflow_run_id": v.run_id,
    }


def confirm(state: CycleState, runtime: Runtime[CycleContext]) -> dict[str, Any]:
    """Confirm the top promising variants on the full validation suite."""
    ctx = _ctx(runtime)
    variants = _copy(state)
    suite = ctx.full_suite
    champion = SolverConfig(**state.champion["config"])
    wall = ctx.budget.limits.wall_clock_seconds
    promising = sorted(
        (v for v in variants if v.status == "promising"),
        key=lambda v: -v.quick.median_rel_improvement,
    )[: state.confirm_top]
    if not promising:
        return {
            "nomination_note": "no variant was promising on the quick suite, so nothing "
            "was confirmed or nominated (a valid result)"
        }
    # Fit the confirmations into the CPU budget, best first.
    chosen, est = [], estimate_cpu_seconds(champion, suite)
    for v in promising:
        e = estimate_cpu_seconds(SolverConfig(**v.config), suite)
        if ctx.budget.cpu_refusal(est + e, "confirmation") is None:
            chosen.append(v)
            est += e
    if not chosen:
        reason = ctx.budget.cpu_refusal(
            est + estimate_cpu_seconds(SolverConfig(**promising[0].config), suite),
            f"confirming {promising[0].vid} (with the champion baseline)",
        )
        return {"stop_reason": reason, "budgets": ctx.budget.snapshot()}
    if len(chosen) < len(promising):
        ctx.say(f"  CPU budget: confirming {len(chosen)} of {len(promising)} promising variants")
    update: dict[str, Any] = {}
    with child_run(
        ctx,
        f"champion baseline full ({suite.split})",
        {"run_kind": "agent_champion_baseline", "suite": suite.name},
    ) as run:
        ev = evaluate_champion(champion, suite, ctx.runner, ctx.git, ctx.champion_ref)
        ctx.budget.add_cpu(fresh_cpu_seconds(ev, wall))
        ctx.champion_evals["full"] = ev
        update["champion_full_run"] = run.info.run_id
    for v in chosen:
        ctx.say(f"  {v.vid} confirmation on full {suite.split}: {v.config_label}")
        with child_run(
            ctx,
            f"{v.vid} confirm full {suite.split}",
            {"run_kind": "agent_confirmation", "variant_id": v.vid, "agent_cycle": state.cycle_id},
            parent=v.run_id,
        ) as run:
            summary, _ = evaluate_candidate(
                SolverConfig(**v.config),
                ev,
                suite,
                ctx.runner,
                ctx.git,
                run.info.run_id,
                wall,
                with_gate_checks=True,
            )
            mlflow.log_metrics(_summary_metrics("full", summary))
        v.full = summary
        ctx.budget.add_cpu(summary.cpu_seconds)
        if summary.wall_clock_exceeded:
            update["stop_reason"] = (
                f"per run wall clock budget ({wall:g} s) exceeded confirming {v.vid}"
            )
            v.status, v.reason = "crashed", "a confirmation run exceeded the wall clock budget"
            break
        failed = [g["gate"] for g in summary.gate_checks if not g["met"]]
        quick = f"quick {_pct(v.quick.median_rel_improvement)}"
        full = (
            f"full validation {_pct(summary.median_rel_improvement)} "
            f"[{_pct(summary.ci_low)}, {_pct(summary.ci_high)}]"
        )
        if failed:
            v.status = "not_confirmed"
            v.reason = f"{quick}; {full}; gate checks not met: {', '.join(failed)}"
        else:
            v.status = "confirmed"
            v.reason = f"{quick}; {full}; every gate check met on full validation"
        ctx.say(f"  {v.vid} {v.status}: {v.reason}")
        MlflowClient().set_tag(v.run_id, "status", v.status)
        MlflowClient().set_tag(v.run_id, "status_reason", v.reason[:5000])
    return update | {"variants": variants, "budgets": ctx.budget.snapshot()}


def nominate(state: CycleState, runtime: Runtime[CycleContext]) -> dict[str, Any]:
    """Nominate at most one challenger: the confirmed variant with the best
    full validation median. Nothing confirmed means nothing nominated."""
    ctx = _ctx(runtime)
    variants = _copy(state)
    confirmed = sorted(
        (v for v in variants if v.status == "confirmed"),
        key=lambda v: -v.full.median_rel_improvement,
    )
    if not confirmed:
        tried = [v for v in variants if v.full is not None]
        note = state.nomination_note or (
            "no confirmed variant met every gate check on full validation, so nothing was "
            "nominated (a valid result; the gates were not changed)"
            if tried
            else "nothing was confirmed, so nothing was nominated"
        )
        return {"nominee": None, "nomination_note": note}
    best = confirmed[0]
    config = SolverConfig(**best.config)
    card = {
        "source": "experiment agent (Module 3)",
        "cycle_id": state.cycle_id,
        "cycle_run_id": ctx.cycle_run_id,
        "variant": best.variant,
        "quick_tune": best.quick.model_dump(),
        "full_validation": best.full.model_dump(),
        "note": "selected on tune, confirmed on validation; the test split is used only by "
        "the promotion gate (Module 4)",
    }
    version = registry.register(
        config,
        f"Challenger nominated by agent cycle {state.cycle_id} ({best.vid} {best.name}).",
        report_card=card,
    )
    registry.set_challenger(version)
    mlflow.set_experiment(experiment_id=ctx.experiment_id)
    best.status = "nominated"
    MlflowClient().set_tag(best.run_id, "status", "nominated")
    nominee = {
        "vid": best.vid,
        "name": best.name,
        "version": version,
        "config": best.config_label,
        "config_key": best.config_key,
        "full_median": best.full.median_rel_improvement,
    }
    ctx.say(f"Nominated {best.vid} as @challenger (routing-solver v{version})")
    return {
        "variants": variants,
        "nominee": nominee,
        "nomination_note": "@challenger set; @champion unchanged until the promotion gate "
        "and human approval (Module 4)",
    }


def finalize(state: CycleState, runtime: Runtime[CycleContext]) -> dict[str, Any]:
    """Write the cycle report on the parent run."""
    ctx = _ctx(runtime)
    note = state.nomination_note
    if state.stop_reason and state.nominee is None:
        note = f"the cycle stopped early ({state.stop_reason}); nothing was nominated"
    elif state.quick_only and state.nominee is None:
        note = "quick phase only (no confirmation), so nothing was nominated by design"
    final = state.model_copy(update={"budgets": ctx.budget.snapshot(), "nomination_note": note})
    extra = {
        "git_commit": ctx.git["commit"],
        "git_dirty": ctx.git["dirty"],
        "mlflow_cycle_run_id": ctx.cycle_run_id,
        "suite_settings": {
            "quick": _suite_info(ctx.quick_suite),
            "full": _suite_info(ctx.full_suite),
        },
    }
    rep = report.build(final, extra)
    client = MlflowClient()
    client.log_dict(ctx.cycle_run_id, rep, "cycle_report.json")
    client.log_text(ctx.cycle_run_id, report.to_markdown(rep), "cycle_report.md")
    return {"report": rep, "budgets": final.budgets, "nomination_note": note}


def _suite_info(s: Any) -> dict[str, Any]:
    return {
        "name": s.name,
        "split": s.split,
        "instances": len(s.refs),
        "instance_names": s.instance_names,
        "seeds": s.seeds,
        "time_limit_s": s.time_limit_s,
        "fingerprint": s.fingerprint(),
    }
