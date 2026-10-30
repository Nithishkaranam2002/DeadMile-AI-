"""Graph state and run context of the experiment agent.

``CycleState`` is plain, serializable data (pydantic), saved by the LangGraph
checkpointer after every node, so Module 4 can pause the graph at the human
approval interrupt and resume it later. ``CycleContext`` holds the live
objects a cycle needs (LLM client, memory, runner, budgets, suites, MLflow
ids); it is passed to every node as LangGraph runtime context.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

from dmlab.agent.budgets import BudgetTracker
from dmlab.agent.llm import LLMClient
from dmlab.agent.memory import ExperimentMemory
from dmlab.harness.evaluate import Evaluation
from dmlab.harness.runners import Runner
from dmlab.harness.suites import Suite

Status = Literal[
    "pending",  # passed screening, waiting to run
    "rejected",  # never ran: invalid, disabled, duplicate, over the cap, or budget
    "crashed",  # ran, but some runs crashed
    "infeasible",  # ran, infeasible on at least one quick run
    "not_better",  # ran, quick median relative improvement <= 0
    "promising",  # ran, feasible everywhere and quick median > 0
    "not_confirmed",  # confirmed on full validation, did not meet the gate checks
    "confirmed",  # met every gate check on full validation
    "nominated",  # the one confirmed variant set as @challenger
]


class EvalSummary(BaseModel):
    """Candidate vs champion on one suite, from logged MLflow runs."""

    suite: str
    split: str
    time_limit_s: float
    seeds: list[int]
    instances: int
    candidate_runs: int
    candidate_feasible_runs: int
    errors: list[str] = Field(default_factory=list)
    wall_clock_exceeded: bool = False
    candidate_feasible_instances: int
    paired: int
    excluded: int
    wins: int
    losses: int
    ties: int
    median_rel_improvement: float | None
    ci_low: float | None
    ci_high: float | None
    p_two_sided: float | None
    runtime_ratio: float | None
    slices: list[dict[str, Any]]
    champion_reused_runs: int
    champion_total_runs: int
    cpu_seconds: float
    run_id: str  # MLflow run holding the report card
    gate_checks: list[dict[str, Any]] | None = None
    gate_checks_met: bool | None = None


class VariantRecord(BaseModel):
    vid: str
    round: int
    status: Status
    reason: str
    raw: Any = None  # the proposal as the LLM returned it
    kind: str | None = None
    name: str = ""
    hypothesis: str = ""
    variant: dict[str, Any] | None = None  # validated variant
    config: dict[str, Any] | None = None  # SolverConfig dump
    config_key: str | None = None
    config_label: str | None = None
    run_id: str | None = None  # child MLflow run of this variant
    proposed_by_call: int | None = None
    llm_share: dict[str, float] = Field(default_factory=dict)
    quick: EvalSummary | None = None
    full: EvalSummary | None = None
    lesson: str | None = None
    memory_id: str | None = None


class CycleState(BaseModel):
    cycle_id: str
    session: str
    model: str
    offline: bool
    quick_only: bool
    confirm_top: int
    round: int = 0
    max_rounds: int = 3
    per_round: int = 4
    champion: dict[str, Any] = Field(default_factory=dict)
    memory_context: list[dict[str, Any]] = Field(default_factory=list)
    hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    variants: list[VariantRecord] = Field(default_factory=list)
    pending: list[str] = Field(default_factory=list)  # vids to run this round
    keep_going: bool = True
    keep_going_reason: str = ""
    stop_reason: str | None = None  # a budget or error ended the cycle early
    end_reason: str | None = None  # why proposing ended normally
    nominee: dict[str, Any] | None = None
    nomination_note: str = ""
    budgets: dict[str, Any] = Field(default_factory=dict)
    llm_calls: list[dict[str, Any]] = Field(default_factory=list)
    champion_quick_run: str | None = None
    champion_full_run: str | None = None
    report: dict[str, Any] | None = None

    def variant(self, vid: str) -> VariantRecord:
        return next(v for v in self.variants if v.vid == vid)


@dataclass
class CycleContext:
    llm: LLMClient
    memory: ExperimentMemory
    runner: Runner
    budget: BudgetTracker
    quick_suite: Suite
    full_suite: Suite
    cycle_run_id: str
    experiment_id: str
    git: dict[str, Any]
    champion_ref: str | None = None
    # Live caches, not part of the checkpointed state.
    champion_evals: dict[str, Evaluation] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)

    def say(self, text: str) -> None:
        print(text, flush=True)
        self.log.append(text)
