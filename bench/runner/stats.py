"""Statistical core for the calibrated baseline (Track-3 P3, spec §4).

The smoke harness compared single retried runs with a heuristic ≥10pp drop. A
calibrated benchmark instead characterises each metric as a *distribution* over N
scored runs (median + bootstrap 95% CI) and gates on whether the challenger's CI is
*disjoint and below* the baseline's — a difference of known false-positive rate rather
than an arbitrary threshold. Stdlib only (no numpy): `random` + `statistics`.
"""
from __future__ import annotations

import math
import random
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MetricCI:
    """A metric's point estimate (median) + bootstrap confidence interval."""

    median: float
    ci_low: float
    ci_high: float


def bootstrap_ci(
    values: Sequence[float],
    *,
    confidence: float = 0.95,
    n_resamples: int = 2000,
    seed: int = 0,
) -> MetricCI:
    """Percentile-bootstrap CI for the *median* of ``values``.

    Resamples with replacement ``n_resamples`` times, takes the median of each
    resample, and reads the (1-confidence)/2 and 1-(1-confidence)/2 percentiles.
    Deterministic given ``seed``. Empty -> all-zero; a degenerate (all-equal or
    single-value) sample collapses the CI to the point. The returned interval is
    clamped so ``ci_low <= median <= ci_high`` always holds.
    """
    vals = [float(v) for v in values]
    if not vals:
        return MetricCI(0.0, 0.0, 0.0)
    point = statistics.median(vals)
    if len(set(vals)) == 1:
        return MetricCI(point, vals[0], vals[0])

    rng = random.Random(seed)
    n = len(vals)
    medians = sorted(statistics.median(rng.choices(vals, k=n)) for _ in range(n_resamples))
    alpha = (1.0 - confidence) / 2.0
    lo = medians[max(0, int(alpha * n_resamples))]
    hi = medians[min(n_resamples - 1, int((1.0 - alpha) * n_resamples))]
    # Guarantee the point estimate sits inside its own interval.
    return MetricCI(point, min(lo, point), max(hi, point))


def wilson_ci(successes: int, n: int, *, confidence: float = 0.95) -> MetricCI:
    """Wilson score interval for a binomial proportion ``successes / n``.

    The gate metric ``critical_recall`` is binary per run (each case has exactly one
    mandatory finding -> caught or not), so a run is a Bernoulli trial. Bootstrap-of-
    median is the *wrong* tool for binary data (roadmap 0.1): on e.g. ``[1,1,1,1,0]`` it
    pins the lower bound at 0, leaving the gate unable to ever fire. The Wilson interval
    is the standard, well-behaved CI for a proportion: it stays inside ``[0, 1]``, never
    collapses to a degenerate point at the boundaries, and tightens as ``n`` grows — so
    the gate's power scales with the number of captured runs. Point estimate = the sample
    proportion (stored in ``median`` for a uniform :class:`MetricCI` shape). ``n == 0``
    yields all-zeros (no data)."""
    if n <= 0:
        return MetricCI(0.0, 0.0, 0.0)
    z = statistics.NormalDist().inv_cdf((1.0 + confidence) / 2.0)
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    margin = (z / denom) * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n))
    lo = max(0.0, center - margin)
    hi = min(1.0, center + margin)
    return MetricCI(p, min(lo, p), max(hi, p))


@dataclass(frozen=True)
class CIRegressionResult:
    failed: bool
    regressed_cases: list[str]
    details: dict[str, str] = field(default_factory=dict)


def ci_regression(
    baseline: dict[str, MetricCI],
    current: dict[str, MetricCI],
    *,
    min_regressed: int = 2,
) -> CIRegressionResult:
    """Blocking-gate rule (spec §4): a case regresses when the challenger's CI is
    *entirely below* the baseline's (``current.ci_high < baseline.ci_low`` — disjoint,
    not merely lower). Overlapping CIs are statistically indistinguishable (no
    regression); a strictly-higher CI is an improvement. Fails when ``>= min_regressed``
    cases regress. Cases absent from ``current`` are skipped here (a total harness
    outage is handled separately as exit 2, not a quality regression)."""
    regressed: list[str] = []
    details: dict[str, str] = {}
    for case, base in baseline.items():
        cur = current.get(case)
        if cur is None:
            continue
        if cur.ci_high < base.ci_low:
            regressed.append(case)
            details[case] = (
                f"current CI [{cur.ci_low:.3f},{cur.ci_high:.3f}] strictly below "
                f"baseline CI [{base.ci_low:.3f},{base.ci_high:.3f}]"
            )
    return CIRegressionResult(
        failed=len(regressed) >= min_regressed,
        regressed_cases=sorted(regressed),
        details=details,
    )


def success_rate(*, n_scored: int, n_attempts: int) -> float:
    """Harness reliability: scored runs / total attempts (0.0 when no attempts)."""
    return n_scored / n_attempts if n_attempts else 0.0
