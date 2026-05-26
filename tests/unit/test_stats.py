"""Statistical core for the calibrated baseline (Track-3 P3, spec §4/§10)."""
from __future__ import annotations

from bench.runner.stats import MetricCI, bootstrap_ci, ci_regression, success_rate

# --- bootstrap_ci ---------------------------------------------------------


def test_empty_returns_zeros() -> None:
    assert bootstrap_ci([]) == MetricCI(0.0, 0.0, 0.0)


def test_single_value_collapses() -> None:
    assert bootstrap_ci([0.5]) == MetricCI(0.5, 0.5, 0.5)


def test_all_equal_collapses_to_point() -> None:
    ci = bootstrap_ci([1.0, 1.0, 1.0, 1.0, 1.0])
    assert ci == MetricCI(1.0, 1.0, 1.0)


def test_median_is_point_estimate() -> None:
    ci = bootstrap_ci([0.0, 0.25, 0.5, 0.75, 1.0])
    assert ci.median == 0.5


def test_ci_low_le_median_le_ci_high() -> None:
    ci = bootstrap_ci([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
    assert ci.ci_low <= ci.median <= ci.ci_high


def test_deterministic_with_fixed_seed() -> None:
    vals = [0.0, 0.3, 0.5, 0.5, 1.0, 0.7, 0.2]
    assert bootstrap_ci(vals, seed=42) == bootstrap_ci(vals, seed=42)


def test_wider_spread_gives_wider_ci() -> None:
    tight = bootstrap_ci([0.5, 0.5, 0.5, 0.5, 0.6, 0.4])
    wide = bootstrap_ci([0.0, 1.0, 0.0, 1.0, 0.5, 0.5])
    assert (wide.ci_high - wide.ci_low) >= (tight.ci_high - tight.ci_low)


# --- ci_regression (non-overlapping CIs = real difference) ---------------


def _ci(lo: float, hi: float, median: float | None = None) -> MetricCI:
    return MetricCI(median if median is not None else (lo + hi) / 2, lo, hi)


def test_overlapping_cis_are_not_a_regression() -> None:
    base = {"c1": _ci(0.8, 1.0), "c2": _ci(0.8, 1.0)}
    cur = {"c1": _ci(0.7, 0.95), "c2": _ci(0.75, 0.98)}  # overlap baseline
    result = ci_regression(base, cur)
    assert not result.failed
    assert result.regressed_cases == []


def test_two_cases_strictly_below_baseline_fail() -> None:
    base = {"c1": _ci(0.8, 1.0), "c2": _ci(0.8, 1.0)}
    cur = {"c1": _ci(0.0, 0.3), "c2": _ci(0.1, 0.4)}  # both CIs entirely below
    result = ci_regression(base, cur)
    assert result.failed
    assert result.regressed_cases == ["c1", "c2"]


def test_single_case_drop_does_not_fail() -> None:
    base = {"c1": _ci(0.8, 1.0), "c2": _ci(0.8, 1.0)}
    cur = {"c1": _ci(0.0, 0.3), "c2": _ci(0.8, 1.0)}  # only c1 regresses
    result = ci_regression(base, cur)
    assert not result.failed
    assert result.regressed_cases == ["c1"]


def test_improvement_is_not_a_regression() -> None:
    base = {"c1": _ci(0.4, 0.6), "c2": _ci(0.4, 0.6)}
    cur = {"c1": _ci(0.9, 1.0), "c2": _ci(0.9, 1.0)}  # strictly above
    result = ci_regression(base, cur)
    assert not result.failed
    assert result.regressed_cases == []


def test_case_missing_from_current_is_not_counted() -> None:
    base = {"c1": _ci(0.8, 1.0), "c2": _ci(0.8, 1.0)}
    cur = {"c1": _ci(0.0, 0.3)}  # c2 absent (e.g. total harness failure for c2)
    result = ci_regression(base, cur)
    assert not result.failed  # only 1 comparable regressed case < min 2
    assert result.regressed_cases == ["c1"]


# --- success_rate ---------------------------------------------------------


def test_success_rate_basic() -> None:
    assert success_rate(n_scored=4, n_attempts=8) == 0.5


def test_success_rate_zero_attempts_is_zero() -> None:
    assert success_rate(n_scored=0, n_attempts=0) == 0.0
