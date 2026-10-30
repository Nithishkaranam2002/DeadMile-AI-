"""Harness self checks. If either fails, the harness has a bug.

1. A/A (a luck test): the champion config with the full suite seeds (1-5)
   against the same config with different seeds (aa_seeds, 6-10). Any
   difference can only be seed luck, so the two sided Wilcoxon p must be at
   least 0.05.
2. OR Tools against the PyVRP champion must show PyVRP as better: median r < 0,
   bootstrap CI upper bound < 0, and two sided p < 0.05.

All three evaluations (champion seeds, champion A/A seeds, OR Tools) run in
one interleaved runner call; the champion evaluation is shared by both checks
and champion runs may be reused from MLflow (see reuse.py). Each check's
report card is logged in its own nested run with a clear name, e.g.
"A/A check: champion vs itself". A failed check is reported as failed. It is
never rerun with other seeds.
"""

from typing import Any

import mlflow
from pydantic import BaseModel

from dmlab.harness.compare import (
    Comparison,
    compare_evaluations,
    log_named_comparison,
    statistics_settings,
)
from dmlab.harness.evaluate import EXPERIMENT, MODULE, EvalSpec, run_evaluations
from dmlab.harness.runners import Runner, SolverConfig
from dmlab.harness.suites import Suite
from dmlab.tracking import configure_mlflow, git_info

ALPHA = 0.05


class CheckResult(BaseModel):
    name: str
    passed: bool
    rule: str
    observed: dict[str, Any]


AA_RUN_NAME = "A/A check: champion vs itself"
AA_NOTE = (
    "Luck test. Both sides are the same champion config; the champion side ran seeds "
    "{seeds} and the other side ran seeds {aa_seeds}. Any difference can only come from "
    "random seed luck, so it must not be statistically significant (two sided p >= 0.05). "
    "Ties are instances where both seed sets reached the same average distance."
)


def check_aa(c: Comparison) -> CheckResult:
    p = c.wilcoxon.p_two_sided
    return CheckResult(
        name="A/A: champion vs itself with different seeds",
        passed=p >= ALPHA,
        rule=f"two sided Wilcoxon p >= {ALPHA}",
        observed={
            "p_two_sided": p,
            "p_greater": c.wilcoxon.p_greater,
            "median_rel_improvement": c.overall.median_rel_improvement,
            "ci": [c.overall.ci_low, c.overall.ci_high],
            "wins_losses_ties": [c.overall.wins, c.overall.losses, c.overall.ties],
        },
    )


def check_champion_beats(c: Comparison) -> CheckResult:
    o, w = c.overall, c.wilcoxon
    passed = (
        o.median_rel_improvement is not None
        and o.median_rel_improvement < 0
        and o.ci_high is not None
        and o.ci_high < 0
        and w.p_two_sided < ALPHA
    )
    return CheckResult(
        name=f"{c.candidate.label} vs champion {c.champion.label}: champion must be better",
        passed=passed,
        rule=f"median r < 0, CI upper bound < 0, two sided p < {ALPHA}",
        observed={
            "p_two_sided": w.p_two_sided,
            "median_rel_improvement": o.median_rel_improvement,
            "ci": [o.ci_low, o.ci_high],
            "wins_losses_ties": [o.wins, o.losses, o.ties],
        },
    )


def run_selfcheck(
    champion: SolverConfig,
    other: SolverConfig,
    suite: Suite,
    aa_seeds: list[int],
    runner: Runner,
    champion_ref: str | None = None,
) -> tuple[list[CheckResult], dict[str, Comparison], str]:
    if set(aa_seeds) & set(suite.seeds):
        raise ValueError("A/A seeds must differ from the suite seeds")
    configure_mlflow()
    mlflow.set_experiment(EXPERIMENT)
    git = git_info().model_dump()
    campaign = f"selfcheck {suite.name}/{suite.split}"
    tags = {
        "run_kind": "selfcheck",
        "dmlab_module": MODULE,
        "suite": suite.name,
        "split": suite.split,
        "suite_fingerprint": suite.fingerprint(),
        "git_commit": git["commit"],
        "git_dirty": str(git["dirty"]).lower(),
    }
    with mlflow.start_run(run_name=f"selfcheck {suite.name}/{suite.split}", tags=tags) as run:
        run_id = run.info.run_id
        mlflow.log_params(
            {
                "suite": suite.name,
                "split": suite.split,
                "seeds": ",".join(map(str, suite.seeds)),
                "aa_seeds": ",".join(map(str, aa_seeds)),
                "time_limit_s": suite.time_limit_s,
                "num_instances": len(suite.refs),
                "workers": getattr(runner, "workers", "n/a"),
                "champion": champion.label(),
                "other": other.label(),
            }
        )
        champ, champ_aa, oth = run_evaluations(
            [
                EvalSpec(
                    group="champion",
                    config=champion,
                    seeds=suite.seeds,
                    registry_ref=champion_ref,
                    reuse=True,
                ),
                EvalSpec(
                    group="champion_aa",
                    config=champion,
                    seeds=aa_seeds,
                    registry_ref=champion_ref,
                    reuse=True,
                ),
                EvalSpec(group=other.solver, config=other, seeds=suite.seeds),
            ],
            suite,
            runner,
            campaign,
            git,
        )
        st = statistics_settings()
        comparisons = {
            "aa": compare_evaluations(champ_aa, champ, st),
            "vs_" + other.solver: compare_evaluations(oth, champ, st),
        }
        named = {
            "aa": (
                AA_RUN_NAME,
                AA_NOTE.format(seeds=suite.seeds, aa_seeds=aa_seeds),
            ),
            "vs_" + other.solver: (
                f"Self check: {other.solver} vs champion",
                "Known answer test: the PyVRP champion must come out better.",
            ),
        }
        card_runs = {}
        for key, c in comparisons.items():
            run_name, note = named[key]
            card_runs[key] = log_named_comparison(
                c, run_name, git, runner, tags={"run_kind": "report_card", "check": key}, note=note
            )
        mlflow.log_dict(card_runs, "report_card_runs.json")
        checks = [
            check_aa(comparisons["aa"]),
            check_champion_beats(comparisons["vs_" + other.solver]),
        ]
        mlflow.log_dict({"checks": [c.model_dump() for c in checks]}, "selfcheck.json")
        mlflow.log_metrics({f"check_{i}_passed": float(c.passed) for i, c in enumerate(checks, 1)})
        mlflow.set_tag("selfcheck_passed", str(all(c.passed for c in checks)).lower())
    return checks, comparisons, run_id
