"""CITATION_THRESHOLD TP/FP sweep + hallucination primitive (Track-3 P5, spec §6)."""
from __future__ import annotations

import hydra.grounding as grounding
from bench.runner.threshold_calibration import (
    _f1_at,
    citation_ratio,
    is_likely_hallucination,
    load_grounding_labels,
    sweep_over_ratios,
    sweep_threshold,
)

# --- citation_ratio (shares the live grounder's tokenization) -------------


def test_citation_ratio_all_tokens_present_is_one() -> None:
    assert citation_ratio("alpha beta gamma", "alpha beta gamma here") == 1.0


def test_citation_ratio_no_tokens_present_is_zero() -> None:
    assert citation_ratio("alpha beta gamma", "totally unrelated snippet") == 0.0


def test_citation_ratio_half_present() -> None:
    # tokens: alpha,beta,gamma,delta (4); snippet has alpha,beta -> 2/4
    assert citation_ratio("alpha beta gamma delta", "alpha beta only") == 0.5


def test_citation_ratio_uses_grounding_tokenizer() -> None:
    # stopwords excluded by the shared tokenizer -> only 'mutex' counts
    assert citation_ratio("the mutex", "mutex guards the section") == 1.0


# --- is_likely_hallucination ----------------------------------------------


def test_hallucination_when_ratio_below_threshold() -> None:
    assert is_likely_hallucination("alpha beta gamma delta", "alpha only", threshold=0.4) is True


def test_not_hallucination_when_grounded() -> None:
    assert is_likely_hallucination("alpha beta", "alpha beta present", threshold=0.4) is False


# --- sweep logic (decoupled from tokenization) ----------------------------


def test_sweep_picks_separating_threshold_midpoint() -> None:
    scored = [(1.0, True), (1.0, True), (0.0, False), (0.0, False)]
    result = sweep_over_ratios(scored, candidates=[round(0.1 * i, 2) for i in range(1, 10)])
    assert result.best_f1 == 1.0
    assert result.best_threshold == 0.5  # median of the perfect-separation plateau


def test_sweep_returned_threshold_actually_achieves_best_f1() -> None:
    # Non-contiguous best-F1 plateau: thresholds 0.2 and 0.5 both hit the max F1, but the
    # midpoint 0.35 between them scores strictly lower. statistics.median([0.2, 0.5]) = 0.35
    # froze a threshold that does NOT realize the claimed best_f1 — an internally inconsistent
    # SweepResult. Invariant: the returned threshold must actually achieve best_f1.
    # (0.15,F) knocks t=0.1 out of the plateau so it is exactly [0.2, 0.5] (even, with a
    # lower-F1 dip at the 0.35 midpoint).
    scored = [(0.25, True), (0.55, True), (0.35, False), (0.45, False), (0.15, False)]
    candidates = [round(0.1 * i, 2) for i in range(1, 7)]  # 0.1 .. 0.6
    result = sweep_over_ratios(scored, candidates=candidates)
    assert _f1_at(scored, result.best_threshold) == result.best_f1


def test_sweep_handles_imperfect_separation() -> None:
    # one hallucinated pair scores as high as the grounded ones -> F1 < 1.0 achievable
    scored = [(0.8, True), (0.9, True), (0.85, False), (0.1, False)]
    result = sweep_over_ratios(scored, candidates=[round(0.1 * i, 2) for i in range(0, 11)])
    assert 0.0 < result.best_f1 <= 1.0
    assert 0.0 <= result.best_threshold <= 1.0


# --- committed label set + calibration provenance -------------------------


def test_grounding_label_set_loads_and_is_balanced() -> None:
    labels = load_grounding_labels()
    assert len(labels) >= 12
    kinds = {ln.label for ln in labels}
    assert kinds == {"grounded", "hallucinated"}
    n_g = sum(1 for ln in labels if ln.label == "grounded")
    third = len(labels) // 3
    assert n_g >= third and (len(labels) - n_g) >= third


def test_sweep_over_real_labels_separates_well() -> None:
    labels = load_grounding_labels()
    result = sweep_threshold(labels)
    assert result.best_f1 >= 0.8, f"label set not separable enough (F1={result.best_f1:.2f})"
    assert 0.0 < result.best_threshold < 1.0


def test_citation_threshold_is_calibrated_to_the_committed_label_set() -> None:
    # the frozen live threshold MUST equal the sweep-chosen value over the committed
    # labels — calibration is reproducible and drift fails here (spec §6: freeze + document)
    result = sweep_threshold(load_grounding_labels())
    assert result.best_threshold == grounding.CITATION_THRESHOLD
