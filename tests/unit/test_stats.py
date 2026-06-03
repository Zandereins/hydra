"""Statistical core for the calibrated baseline (Track-3 P3, spec §4/§10)."""
from __future__ import annotations

import math

from bench.runner.stats import (
    MetricCI,
    bootstrap_ci,
    ci_regression,
    newcombe_diff_ci,
    success_rate,
    wilson_ci,
)

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


# --- wilson_ci (proportion CI for the binary critical_recall gate) --------


def test_wilson_empty_returns_zeros() -> None:
    assert wilson_ci(0, 0) == MetricCI(0.0, 0.0, 0.0)


def test_wilson_point_is_the_sample_proportion() -> None:
    assert wilson_ci(4, 5).median == 0.8


def test_wilson_bounds_are_clamped_to_unit_interval() -> None:
    ci = wilson_ci(2, 5)
    assert 0.0 <= ci.ci_low <= ci.median <= ci.ci_high <= 1.0


def test_wilson_all_success_is_not_certain_at_small_n() -> None:
    # 5/5 is NOT proof of a perfect detector — the honest lower bound is well below 1.
    ci = wilson_ci(5, 5)
    assert ci.median == 1.0
    assert ci.ci_high == 1.0
    assert ci.ci_low < 1.0


def test_wilson_zero_success_has_upper_bound_below_half() -> None:
    ci = wilson_ci(0, 5)
    assert ci.median == 0.0
    assert 0.0 < ci.ci_high < 0.5


def test_wilson_more_data_tightens_the_interval() -> None:
    narrow = wilson_ci(20, 20)
    wide = wilson_ci(5, 5)
    assert (narrow.ci_high - narrow.ci_low) < (wide.ci_high - wide.ci_low)


def test_wilson_fixes_the_binary_blindness_bootstrap_cannot_see() -> None:
    # The bug (roadmap 0.1): bootstrap-of-median on a binary metric is blind. A single
    # flaky miss in an otherwise-perfect baseline opens its CI to [0, 1], after which no
    # challenger can ever be "strictly below" -> the gate can never fire.
    blind = bootstrap_ci([1.0, 1.0, 1.0, 1.0, 0.0])
    assert blind.ci_low == 0.0  # 4/5 baseline -> lower bound pinned at 0 -> gate dead

    # Wilson treats the same data as a proportion: its lower bound is meaningfully > 0,
    # so a genuine drop becomes detectable, and the interval is disjoint from a real
    # regression at adequate N (20/20 vs 4/20).
    assert wilson_ci(4, 5).ci_low > 0.0
    assert wilson_ci(4, 20).ci_high < wilson_ci(20, 20).ci_low


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


# --- newcombe_diff_ci (non-inferiority difference CI, crypto-FN re-test) ---


def test_newcombe_matches_published_example() -> None:
    # Newcombe (1998) worked example: p1=56/70=0.8 vs p2=48/80=0.6, diff=+0.2.
    # Published MOVER 95% CI ~ [0.05, 0.33]. We compute D = p_b - p_a with b=56/70 (the
    # higher arm) and a=48/80. The interval is asymmetric about the point diff (Wilson
    # bounds are skewed), so we check the published endpoints directly, not the midpoint.
    lo, hi = newcombe_diff_ci(48, 80, 56, 70)
    assert abs(lo - 0.053) < 0.01
    assert abs(hi - 0.332) < 0.01


def test_newcombe_point_diff_is_centered_between_bounds() -> None:
    # The interval straddles the observed difference p_b - p_a.
    lo, hi = newcombe_diff_ci(6, 10, 9, 10)  # pa=0.6, pb=0.9, diff=+0.3
    assert lo < 0.3 < hi


def test_newcombe_symmetric_equal_arms_centered_on_zero() -> None:
    lo, hi = newcombe_diff_ci(8, 10, 8, 10)  # identical arms -> diff 0
    assert lo < 0.0 < hi
    assert abs(lo + hi) < 1e-9  # symmetric about 0 when arms are identical


def test_newcombe_more_data_tightens_interval() -> None:
    narrow_lo, narrow_hi = newcombe_diff_ci(40, 50, 45, 50)
    wide_lo, wide_hi = newcombe_diff_ci(4, 5, 4, 5)
    assert (narrow_hi - narrow_lo) < (wide_hi - wide_lo)


def test_newcombe_lower_bound_pairs_treatment_drop_with_control_rise() -> None:
    # The load-bearing pairing: lo = diff - sqrt[(p_b - l_b)^2 + (u_a - p_a)^2].
    # Re-derive it independently and assert the implementation matches (a mispaired
    # a<->b swap — the design-spec's bug — would diverge here).
    a, na, b, nb = 13, 15, 15, 15  # control 0.8667, treatment 1.0
    ca, cb = wilson_ci(a, na), wilson_ci(b, nb)
    pa, pb = a / na, b / nb
    expected_lo = (pb - pa) - math.sqrt((pb - cb.ci_low) ** 2 + (ca.ci_high - pa) ** 2)
    lo, _ = newcombe_diff_ci(a, na, b, nb)
    assert abs(lo - expected_lo) < 1e-12


def test_newcombe_detects_real_over_suppression() -> None:
    # control 15/15, treatment 8/15: a genuine ~47pp drop -> upper bound well below 0.
    lo, hi = newcombe_diff_ci(15, 15, 8, 15)
    assert hi < 0.0  # treatment confidently worse -> would REOPEN the caveat
    assert lo < -0.15


def test_newcombe_zero_n_arm_degrades_to_point() -> None:
    lo, hi = newcombe_diff_ci(0, 0, 5, 5)  # empty control arm
    assert -1.0 <= lo <= hi <= 1.0


# --- success_rate ---------------------------------------------------------


def test_success_rate_basic() -> None:
    assert success_rate(n_scored=4, n_attempts=8) == 0.5


def test_success_rate_zero_attempts_is_zero() -> None:
    assert success_rate(n_scored=0, n_attempts=0) == 0.0
