"""Gate thresholds applied as information only, on hand made comparisons.
Values are fixtures, not results."""

import pytest

from dmlab.harness.compare import compare_evaluations
from dmlab.harness.gate_preview import preview
from dmlab.paths import load_config
from tests.test_stats import ST, _ev, _run

GATES = load_config("gates")


def _comparison(candidate_distances: dict[str, float], feasible: bool = True):
    names = list(candidate_distances)
    champion = _ev(
        "champion",
        "pyvrp",
        [_run(n, "C1" if i % 2 else "R1", 1, 100.0) for i, n in enumerate(names)],
        [1],
    )
    candidate = _ev(
        "candidate",
        "nn",
        [
            _run(n, "C1" if i % 2 else "R1", 1, d, feasible=feasible or i > 0)
            for i, (n, d) in enumerate(candidate_distances.items())
        ],
        [1],
    )
    return compare_evaluations(candidate, champion, ST)


def _met(checks):
    return {c.gate: c.met for c in checks}


def test_clear_improvement_meets_every_gate():
    # Eight instances, each 2% to 3% shorter: two sided p = 2/256.
    c = _comparison({f"I{i}": 97.0 + 0.1 * i for i in range(8)})
    met = _met(preview(c, GATES))
    assert all(met.values()), met


def test_too_few_pairs_cannot_pass_wilcoxon():
    # Five instances all better still give p = 1/16 > 0.05.
    c = _comparison({f"I{i}": 97.0 - 0.1 * i for i in range(5)})
    met = _met(preview(c, GATES))
    assert met["improvement: Wilcoxon"] is False
    assert met["improvement: median"] is True


def test_small_improvement_and_slice_regression():
    # Median +0.2% (below 0.5%), and slice R1 is 1% worse.
    c = _comparison({"A": 101.0, "B": 99.8, "C": 101.0, "D": 99.8, "E": 99.0, "F": 99.8})
    met = _met(preview(c, GATES))
    assert met["improvement: median"] is False
    assert met["regression"] is False


def test_infeasible_candidate_fails_feasibility():
    c = _comparison({f"I{i}": 97.0 - 0.1 * i for i in range(8)}, feasible=False)
    assert _met(preview(c, GATES))["feasibility"] is False


def test_gates_use_two_sided_p():
    assert GATES["improvement"]["wilcoxon_alternative"] == "two-sided"
    bad = {**GATES, "improvement": {**GATES["improvement"], "wilcoxon_alternative": "greater"}}
    with pytest.raises(ValueError):
        preview(_comparison({"A": 99.0}), bad)
