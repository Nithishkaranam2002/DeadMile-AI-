"""Agent budgets from configs/budgets.yaml (or the DMLAB_BUDGETS_FILE override).

* per_run.wall_clock_seconds: enforced in the solver worker (harness.runners);
  an overrun ends the cycle here with that reason.
* per_cycle.max_variants: proposals counted per cycle, valid or not. Extra
  proposals are rejected and logged.
* per_cycle.max_cpu_minutes: sum of solver run times (every solver is single
  threaded). A batch is estimated before it starts (tasks x time limit) and
  does not start when it would not fit.
* per_session.llm_max_tokens / llm_max_usd: summed over every cycle of a
  session (earlier cycles are read back from MLflow). Each call is checked
  with its worst case before it is made.

Hitting a budget never raises out of the agent: the node records a stop
reason and the graph goes straight to the report. Budgets are rules, not
results; never change them to make a run fit.
"""

from typing import Any

from pydantic import BaseModel

from dmlab.paths import budgets_config, budgets_path


class BudgetLimits(BaseModel):
    wall_clock_seconds: float | None
    max_variants: int
    max_cpu_minutes: float
    llm_max_tokens: int
    llm_max_usd: float
    source: str

    @classmethod
    def load(cls) -> "BudgetLimits":
        data = budgets_config()
        run, cycle, sess = (data.get(k) or {} for k in ("per_run", "per_cycle", "per_session"))
        missing = [
            name
            for name, value in (
                ("per_cycle.max_variants", cycle.get("max_variants")),
                ("per_cycle.max_cpu_minutes", cycle.get("max_cpu_minutes")),
                ("per_session.llm_max_tokens", sess.get("llm_max_tokens")),
                ("per_session.llm_max_usd", sess.get("llm_max_usd")),
            )
            if value is None
        ]
        if missing:
            raise ValueError(f"budgets not set in {budgets_path()}: {missing}")
        return cls(
            wall_clock_seconds=run.get("wall_clock_seconds"),
            max_variants=int(cycle["max_variants"]),
            max_cpu_minutes=float(cycle["max_cpu_minutes"]),
            llm_max_tokens=int(sess["llm_max_tokens"]),
            llm_max_usd=float(sess["llm_max_usd"]),
            source=str(budgets_path()),
        )


class BudgetTracker:
    def __init__(
        self, limits: BudgetLimits, session_tokens: int = 0, session_usd: float = 0.0
    ) -> None:
        self.limits = limits
        self.prior_session_tokens = session_tokens
        self.prior_session_usd = session_usd
        self.cycle_tokens = 0
        self.cycle_usd = 0.0
        self.cpu_seconds = 0.0
        self.variants_proposed = 0

    # LLM ---------------------------------------------------------------
    @property
    def session_tokens(self) -> int:
        return self.prior_session_tokens + self.cycle_tokens

    @property
    def session_usd(self) -> float:
        return self.prior_session_usd + self.cycle_usd

    def llm_refusal(self, worst_tokens: int, worst_usd: float) -> str | None:
        """Reason the next LLM call may not run, or None."""
        lim = self.limits
        if self.session_tokens + worst_tokens > lim.llm_max_tokens:
            return (
                f"LLM token budget: session used {self.session_tokens} of "
                f"{lim.llm_max_tokens} tokens; the next call could use up to {worst_tokens}"
            )
        if self.session_usd + worst_usd > lim.llm_max_usd:
            return (
                f"LLM dollar budget: session spent ${self.session_usd:.4f} of "
                f"${lim.llm_max_usd:.2f}; the next call could cost up to ${worst_usd:.4f}"
            )
        return None

    def add_llm(self, tokens: int, usd: float) -> None:
        self.cycle_tokens += tokens
        self.cycle_usd += usd

    # Variants ----------------------------------------------------------
    def variant_slots_left(self) -> int:
        return max(0, self.limits.max_variants - self.variants_proposed)

    # CPU ---------------------------------------------------------------
    def cpu_minutes_left(self) -> float:
        return self.limits.max_cpu_minutes - self.cpu_seconds / 60

    def cpu_refusal(self, estimate_s: float, what: str) -> str | None:
        if self.cpu_seconds + estimate_s > self.limits.max_cpu_minutes * 60:
            return (
                f"CPU budget: {what} needs about {estimate_s / 60:.1f} CPU min, "
                f"{self.cpu_minutes_left():.1f} of {self.limits.max_cpu_minutes:g} left this cycle"
            )
        return None

    def add_cpu(self, seconds: float) -> None:
        self.cpu_seconds += seconds

    def snapshot(self) -> dict[str, Any]:
        lim = self.limits
        return {
            "source": lim.source,
            "limits": lim.model_dump(exclude={"source"}),
            "used": {
                "variants_proposed": self.variants_proposed,
                "cpu_minutes": round(self.cpu_seconds / 60, 3),
                "cycle_llm_tokens": self.cycle_tokens,
                "cycle_llm_usd": round(self.cycle_usd, 6),
                "session_llm_tokens": self.session_tokens,
                "session_llm_usd": round(self.session_usd, 6),
            },
        }
