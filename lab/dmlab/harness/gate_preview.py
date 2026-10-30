"""Gate thresholds from configs/gates.yaml, applied to a comparison as
information only. This is not a promotion decision: the real promotion gate
(test split, human approval) comes in Module 4 and will reuse these checks.

The primary metric is total distance. Other metrics are never used here.
"""

from typing import Any

from pydantic import BaseModel

from dmlab.harness.compare import Comparison
from dmlab.paths import load_config

RUNTIME_NOTE = (
    "weak check for solvers that always run until their time limit (PyVRP, OR Tools): "
    "both sides use the same limit, so the ratio is close to 1 by construction"
)


class GateCheck(BaseModel):
    gate: str
    rule: str
    observed: str
    met: bool
    note: str = ""


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{100 * v:+.3f}%"


def preview(c: Comparison, gates: dict[str, Any] | None = None) -> list[GateCheck]:
    g = gates or load_config("gates")
    o, w = c.overall, c.wilcoxon
    imp, reg, rt = g["improvement"], g["regression"], g["runtime"]
    if imp["wilcoxon_alternative"] != "two-sided":
        raise ValueError("gates.yaml improvement.wilcoxon_alternative must be two-sided")
    min_share = g["feasibility"]["min_feasible_share"]
    feas_share = o.candidate_feasible_instances / o.instances if o.instances else 0.0
    m = o.median_rel_improvement
    worst = min(
        (s for s in c.slices if s.median_rel_improvement is not None),
        key=lambda s: s.median_rel_improvement,
        default=None,
    )
    return [
        GateCheck(
            gate="feasibility",
            rule=f"candidate feasible on every run of >= {min_share:.0%} of instances",
            observed=f"{o.candidate_feasible_instances} of {o.instances} ({feas_share:.0%})",
            met=feas_share >= min_share,
        ),
        GateCheck(
            gate="improvement: median",
            rule=f"median relative distance improvement >= "
            f"{100 * imp['min_median_relative_improvement']:.1f}%",
            observed=_pct(m),
            met=m is not None and m >= imp["min_median_relative_improvement"],
        ),
        GateCheck(
            gate="improvement: Wilcoxon",
            rule=f"two sided Wilcoxon p < {imp['max_wilcoxon_p_value']}",
            observed=f"p = {w.p_two_sided:.3g}",
            met=w.p_two_sided < imp["max_wilcoxon_p_value"],
        ),
        GateCheck(
            gate="improvement: bootstrap CI",
            rule=f"lower bound of the {imp['ci_level']:.0%} CI of the median > "
            f"{imp['min_ci_lower_bound']}",
            observed=_pct(o.ci_low),
            met=o.ci_low is not None and o.ci_low > imp["min_ci_lower_bound"],
        ),
        GateCheck(
            gate="regression",
            rule=f"no slice median worse than -{100 * reg['max_slice_regression']:.1f}%",
            observed=(
                f"worst slice {worst.slice}: {_pct(worst.median_rel_improvement)}"
                if worst
                else "n/a"
            ),
            met=worst is not None and worst.median_rel_improvement >= -reg["max_slice_regression"],
            note="slices hold 3 to 7 instances, so slice medians are noisy",
        ),
        GateCheck(
            gate="runtime",
            rule=f"candidate runtime <= {rt['max_runtime_ratio']} x champion runtime",
            observed="n/a" if o.runtime_ratio is None else f"{o.runtime_ratio:.2f} x",
            met=o.runtime_ratio is not None and o.runtime_ratio <= rt["max_runtime_ratio"],
            note=RUNTIME_NOTE,
        ),
    ]
