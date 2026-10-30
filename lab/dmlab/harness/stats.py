"""Paired statistics for candidate vs champion. Pure functions, no I/O.

Sign convention everywhere: relative improvement
    r = (champion - candidate) / champion
so r > 0 means the candidate is better (shorter distance), r < 0 worse.

* Seeds are averaged per instance first, then one r per instance.
* Wilcoxon signed rank on the r values (scipy, zero_method "wilcox": exact
  zeros are ties, dropped and counted). One sided "greater" (candidate better)
  is what the gate uses; "less" and two sided are reported too.
* Bootstrap CI of the median r: resample instances with replacement, seeded,
  percentile interval.
"""

import warnings
from collections.abc import Sequence

import numpy as np
from pydantic import BaseModel
from scipy.stats import wilcoxon


class WilcoxonResult(BaseModel):
    n: int  # paired instances
    n_nonzero: int  # instances that are not ties
    statistic: float | None
    p_greater: float  # H1: candidate better
    p_less: float  # H1: candidate worse
    p_two_sided: float
    method: str


class WinLossTie(BaseModel):
    wins: int  # candidate shorter
    losses: int  # candidate longer
    ties: int  # exactly equal


def seed_mean(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("no values to average")
    return float(np.mean(values))


def relative_improvement(champion: float, candidate: float) -> float:
    if champion <= 0:
        raise ValueError("champion distance must be positive")
    return (champion - candidate) / champion


def win_loss_tie(r: Sequence[float]) -> WinLossTie:
    a = np.asarray(r, dtype=float)
    return WinLossTie(wins=int((a > 0).sum()), losses=int((a < 0).sum()), ties=int((a == 0).sum()))


def wilcoxon_test(r: Sequence[float]) -> WilcoxonResult:
    a = np.asarray(r, dtype=float)
    nonzero = int((a != 0).sum())
    if nonzero == 0:
        # No evidence either way (scipy would divide by zero here).
        return WilcoxonResult(
            n=len(a),
            n_nonzero=0,
            statistic=None,
            p_greater=1.0,
            p_less=1.0,
            p_two_sided=1.0,
            method="no non-zero differences",
        )
    with warnings.catch_warnings():
        # scipy's "auto" computes a normal z even when it then uses an exact test.
        warnings.simplefilter("ignore", RuntimeWarning)
        res = {
            alt: wilcoxon(a, zero_method="wilcox", alternative=alt, method="auto")
            for alt in ("greater", "less", "two-sided")
        }
    return WilcoxonResult(
        n=len(a),
        n_nonzero=nonzero,
        statistic=float(res["greater"].statistic),
        p_greater=float(res["greater"].pvalue),
        p_less=float(res["less"].pvalue),
        p_two_sided=float(res["two-sided"].pvalue),
        method=_scipy_auto_method(a),
    )


def _scipy_auto_method(a: np.ndarray) -> str:
    """Which test scipy 1.18's method="auto" ran (mirrors scipy/stats/_wilcoxon.py)."""
    nz = a[a != 0]
    has_ties = len(np.unique(np.abs(nz))) < len(nz)
    if len(a) > 50:
        return "normal approximation"
    if not has_ties and len(nz) == len(a):
        return "exact"
    if len(a) <= 13:
        return "exact permutation (ties or zeros)"
    return "normal approximation (ties or zeros)"


def bootstrap_median_ci(
    r: Sequence[float], level: float = 0.95, resamples: int = 10_000, seed: int = 0
) -> tuple[float, float] | None:
    a = np.asarray(r, dtype=float)
    if len(a) == 0:
        return None
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(a), size=(resamples, len(a)))
    medians = np.median(a[idx], axis=1)
    alpha = (1 - level) / 2
    lo, hi = np.quantile(medians, [alpha, 1 - alpha])
    return float(lo), float(hi)


def median(r: Sequence[float]) -> float | None:
    return float(np.median(r)) if len(r) else None
