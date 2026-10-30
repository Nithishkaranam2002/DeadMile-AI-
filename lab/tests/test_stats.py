"""Statistics on small hand made data where the right answer is known.
Values are fixtures, not results."""

import pytest

from dmlab.harness import stats
from dmlab.harness.compare import compare_evaluations
from dmlab.harness.evaluate import Evaluation, InstanceRun
from dmlab.harness.runners import SolverConfig

ST = {
    "bootstrap_resamples": 2000,
    "bootstrap_seed": 7,
    "ci_level": 0.95,
    "slice_order": ["C1", "R1"],
}


def test_relative_improvement_sign():
    assert stats.relative_improvement(100, 90) == pytest.approx(0.10)
    assert stats.relative_improvement(100, 110) == pytest.approx(-0.10)
    assert stats.relative_improvement(100, 100) == 0
    with pytest.raises(ValueError):
        stats.relative_improvement(0, 1)


def test_seed_mean():
    assert stats.seed_mean([100, 102, 104]) == 102
    with pytest.raises(ValueError):
        stats.seed_mean([])


def test_wilcoxon_all_better_exact():
    # Five positive, distinct differences: W+ = 15 is the most extreme of 2^5
    # sign patterns, so the exact one sided p is 1/32 and two sided 2/32.
    w = stats.wilcoxon_test([0.01, 0.02, 0.03, 0.04, 0.05])
    assert w.p_greater == pytest.approx(1 / 32)
    assert w.p_two_sided == pytest.approx(2 / 32)
    assert w.p_less == pytest.approx(1.0)
    assert w.statistic == 15 and w.method == "exact"


def test_wilcoxon_all_worse_exact():
    w = stats.wilcoxon_test([-0.05, -0.04, -0.03, -0.02, -0.01])
    assert w.p_less == pytest.approx(1 / 32)
    assert w.p_greater == pytest.approx(1.0)


def test_wilcoxon_mixed_signs_exact():
    # Ranks 1..4; only rank 1 negative: W+ = 9. Patterns with W+ >= 9 out of 16:
    # {2,3,4} = 9 and {1,2,3,4} = 10 -> p = 2/16.
    w = stats.wilcoxon_test([-0.01, 0.02, 0.03, 0.04])
    assert w.statistic == 9
    assert w.p_greater == pytest.approx(2 / 16)


def test_wilcoxon_ties_are_dropped():
    # Two exact ties are dropped; the three remaining all favour the candidate:
    # p = 1/8 from 2^3 sign patterns.
    w = stats.wilcoxon_test([0.0, 0.0, 0.01, 0.02, 0.03])
    assert w.n == 5 and w.n_nonzero == 3
    assert w.p_greater == pytest.approx(1 / 8)


def test_wilcoxon_all_ties_is_no_evidence():
    w = stats.wilcoxon_test([0.0, 0.0, 0.0])
    assert (w.p_greater, w.p_less, w.p_two_sided) == (1.0, 1.0, 1.0)
    assert w.statistic is None


def test_win_loss_tie():
    assert stats.win_loss_tie([0.1, -0.2, 0.0, 0.0, 0.3]).model_dump() == {
        "wins": 2,
        "losses": 1,
        "ties": 2,
    }


def test_bootstrap_constant_and_single():
    assert stats.bootstrap_median_ci([0.02] * 7) == pytest.approx((0.02, 0.02))
    assert stats.bootstrap_median_ci([-0.5]) == pytest.approx((-0.5, -0.5))
    assert stats.bootstrap_median_ci([]) is None


def test_bootstrap_is_seeded_and_bounded():
    r = [0.01 * i for i in range(1, 10)]
    a = stats.bootstrap_median_ci(r, resamples=3000, seed=3)
    assert a == stats.bootstrap_median_ci(r, resamples=3000, seed=3)
    lo, hi = a
    assert min(r) <= lo <= stats.median(r) <= hi <= max(r)


def test_bootstrap_two_values():
    # Median of a resample of {0, 1} (n=2) is 0, 0.5 or 1 with probability
    # 1/4, 1/2, 1/4, so the 95% percentile interval is exactly [0, 1].
    assert stats.bootstrap_median_ci([0.0, 1.0], resamples=20_000, seed=1) == (0.0, 1.0)


def _run(name, slc, seed, dist, feasible=True, seed_used=True):
    return InstanceRun(
        instance=name,
        slice=slc,
        source="fixture",
        seed=seed,
        seed_used=seed_used,
        feasible=feasible,
        total_distance=dist,
        vehicles_used=1,
        runtime_s=1.0,
        distance_unit="unit",
        distance_label="test fixture",
        labels=["fixture"],
        data_version="fixture",
        run_id=None,
    )


def _ev(group, solver, runs, seeds):
    return Evaluation(
        group=group,
        config=SolverConfig(solver=solver),
        registry_ref=None,
        suite_name="full",
        split="validation",
        suite_fingerprint="x",
        time_limit_s=1.0,
        seeds_run=seeds,
        seed_policy="test",
        runs=runs,
        run_id="r",
    )


def test_compare_pairs_seed_means_and_excludes_infeasible():
    champion = _ev(
        "champion",
        "pyvrp",
        [
            _run("A", "C1", 1, 100),
            _run("A", "C1", 2, 102),  # mean 101
            _run("B", "C1", 1, 200),
            _run("B", "C1", 2, 200),  # mean 200
            _run("C", "R1", 1, 50),
            _run("C", "R1", 2, 60, feasible=False),
            _run("D", "R1", 1, 80),
            _run("D", "R1", 2, 80),  # mean 80
        ],
        [1, 2],
    )
    # Seedless candidate: one run per instance.
    candidate = _ev(
        "candidate",
        "nn",
        [
            _run("A", "C1", 1, 90.9, seed_used=False),  # r = 0.1, win
            _run("B", "C1", 1, 200, seed_used=False),  # tie
            _run("C", "R1", 1, 40, seed_used=False),  # excluded: champion infeasible
            _run("D", "R1", 1, 88, seed_used=False),  # r = -0.1, loss
        ],
        [1],
    )
    c = compare_evaluations(candidate, champion, ST)
    by = {i.instance: i for i in c.instances}
    assert by["A"].champion_distance == 101
    assert by["A"].rel_improvement == pytest.approx(0.1)
    assert by["A"].outcome == "win" and by["B"].outcome == "tie"
    assert by["D"].rel_improvement == pytest.approx(-0.1) and by["D"].outcome == "loss"
    assert by["C"].outcome == "excluded" and "champion feasible on 1/2" in by["C"].note
    o = c.overall
    assert (o.instances, o.paired, o.excluded) == (4, 3, 1)
    assert (o.wins, o.losses, o.ties) == (1, 1, 1)
    assert o.median_rel_improvement == pytest.approx(0.0)
    assert [s.slice for s in c.slices] == ["C1", "R1"]
    c1, r1 = c.slices
    assert (c1.wins, c1.ties, c1.paired) == (1, 1, 2)
    assert (r1.losses, r1.excluded, r1.champion_feasible_instances) == (1, 1, 1)
    assert c.wilcoxon.n == 3 and c.wilcoxon.n_nonzero == 2


def test_compare_refuses_mismatched_suites():
    a = _ev("champion", "pyvrp", [_run("A", "C1", 1, 100)], [1])
    b = _ev("candidate", "nn", [_run("Z", "C1", 1, 100)], [1])
    with pytest.raises(ValueError):
        compare_evaluations(b, a, ST)
