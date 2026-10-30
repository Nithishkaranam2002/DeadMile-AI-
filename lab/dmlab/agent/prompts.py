"""Prompts and LLM output schemas of the experiment agent.

Prompts are built only from lab data (champion config, suite settings,
budgets, past experiments, this cycle's results). No environment values, keys
or test split information ever go into a prompt.
"""

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from dmlab.agent.variants import FIRST_SOLUTION_STRATEGIES, METAHEURISTICS
from dmlab.routing.pyvrp_solver import OPERATOR_NAMES


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement: str = Field(min_length=10, max_length=600)
    reasoning: str = Field(min_length=10, max_length=1200)
    variant_kind: Literal["parameter", "formulation", "code"]


class HypothesisSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hypotheses: list[Hypothesis] = Field(min_length=1, max_length=4)


class Lesson(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vid: str
    lesson: str = Field(min_length=5, max_length=600)


class Reflection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lessons: list[Lesson]
    continue_search: bool
    reason: str = Field(min_length=5, max_length=600)


SYSTEM = f"""You are the experiment agent of DeadMile AI's pickup and delivery lab.
You propose and test changes to a vehicle routing solver configuration (the
challenger) against the current champion configuration.

The problem: one depot, identical trucks with capacity and shift length, stops
with time windows and service times. Benchmarks: Solomon VRPTW instances
(abstract distance units, not miles) and Amazon Last Mile routes (haversine
km, delivery only). The primary metric is total distance; a result counts
only if every route is feasible, checked by our own checker.

Fixed rules you cannot change:
- The time limit per run is fixed by the suite. Never propose a time limit,
  runtime or iteration budget that replaces it; such proposals are rejected.
- You screen on the quick suite (a subset of the tune split, short time
  limit, 2 seeds). The best 1 or 2 promising variants are then confirmed on
  the full validation suite at a longer time limit. You never see the test
  split; a later promotion gate uses it.
- Formulation variants change only how the solver sees the problem (they
  tighten it: buffers, fewer vehicles, reserved capacity). Results are always
  measured on the original problem, so tightening usually costs distance.
- Code variants are disabled until the sandbox exists; they are rejected.
- Exact repeats of a config already tested against this champion are rejected.
- Invalid proposals are rejected, never repaired. Reply with JSON only,
  matching the schema you are given.

Parameter variants (PyVRP 0.14, iterated local search with late acceptance;
there is no population or crossover):
- ils: num_iters_no_improvement (1000..1000000, default 150000),
  history_length (1..5000, default 300), exhaustive_on_best (default true)
- penalty: solutions_between_updates (10..10000, default 500),
  penalty_increase (1..5, default 1.5), penalty_decrease (0.1..1, default 0.9),
  target_feasible (0.05..0.95, default 0.65), feas_tolerance (0..0.5, default 0.05)
- neighbourhood: weight_wait_time (0..5, default 0.2), num_neighbours (5..100,
  default 50), symmetric_proximity (default true)
- perturbation: min_perturbations (1..100, default 1), max_perturbations
  (1..100, default 25)
- operators: a subset of {list(OPERATOR_NAMES)}
Or OR Tools: first_solution_strategy in {list(FIRST_SOLUTION_STRATEGIES)},
local_search_metaheuristic in {list(METAHEURISTICS)}.

Formulation variants: tw_late_buffer_share (0..0.5), max_route_duration_factor
(0.5..1), fleet_size_delta (-10..0), capacity_reserve_share (0..0.5).

Good experiments change one idea at a time, learn from past results, and do
not repeat what already failed. Finding no improvement is a valid result.
"""


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=1, sort_keys=True, default=str)


def context_block(state: Any, suites: dict[str, Any], budget: dict[str, Any]) -> str:
    return "\n".join(
        [
            "## Champion",
            _dump(state.champion),
            "## Suites",
            _dump(suites),
            "## Budget",
            _dump(budget),
            "## Similar past experiments (from memory)",
            _dump(state.memory_context) if state.memory_context else "none yet",
            "## This cycle so far",
            _dump([cycle_view(v) for v in state.variants]) if state.variants else "nothing yet",
        ]
    )


def cycle_view(v: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "vid": v.vid,
        "name": v.name,
        "kind": v.kind,
        "status": v.status,
        "reason": v.reason,
        "config": v.config_label,
    }
    if v.quick:
        out["quick"] = {
            "median_rel_improvement": v.quick.median_rel_improvement,
            "ci": [v.quick.ci_low, v.quick.ci_high],
            "wins_losses_ties": [v.quick.wins, v.quick.losses, v.quick.ties],
            "feasible_runs": f"{v.quick.candidate_feasible_runs}/{v.quick.candidate_runs}",
            "slices": v.quick.slices,
        }
    if v.lesson:
        out["lesson"] = v.lesson
    return out


def hypothesize_messages(ctx_text: str, n: int) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": f"{ctx_text}\n\n## Task\nWrite up to {min(n, 4)} hypotheses about what "
            "could make the challenger beat the champion on total distance within the fixed "
            "time limit. Say which variant kind each would be tested with. Use the past "
            "experiments: do not restate ideas that already failed.",
        },
    ]


def propose_messages(
    ctx_text: str, hypotheses: list[dict[str, Any]], n: int, similar: list[dict[str, Any]]
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": f"{ctx_text}\n\n## Hypotheses for this round\n{_dump(hypotheses)}\n\n"
            f"## Past experiments similar to these hypotheses\n"
            f"{_dump(similar) if similar else 'none'}\n\n"
            f"## Task\nPropose exactly {n} variants that test these hypotheses. Each needs "
            "kind, name, hypothesis, rationale, expected_effect, and its settings. Change only "
            "what the hypothesis needs; unset settings keep the champion's defaults.",
        },
    ]


def reflect_messages(ctx_text: str, vids: list[str], can_continue: bool) -> list[dict[str, str]]:
    more = (
        "Say whether another round of proposals is worth it."
        if can_continue
        else "No more rounds are possible this cycle; set continue_search to false."
    )
    return [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": f"{ctx_text}\n\n## Task\nWrite one short lesson for each of these "
            f"variants: {vids}. A lesson says what the result means for future experiments, "
            f"based only on the numbers shown. {more}",
        },
    ]
