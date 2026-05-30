"""Judge calibration harness — accuracy/bias + stability (Track-3 P4, spec §5/§10)."""
from __future__ import annotations

from bench.runner.judge_eval import (
    GoldPair,
    JudgeMetrics,
    evaluate_judge,
    judge_stability,
    load_gold_set,
)
from bench.runner.scoring import Judge


def _pair(expected: str, predict: bool) -> GoldPair:
    """A gold pair whose candidate carries a hidden `_predict` an oracle judge echoes,
    so we control the (expected, predicted) confusion cell exactly."""
    return GoldPair(
        gt={"file": "a.ts", "lines": "1", "must_mention": ["x"], "description": "bug"},
        candidate={"title": "c", "file": "a.ts", "lines": "1", "_predict": predict},
        expected=expected,  # type: ignore[arg-type]
    )


def _oracle() -> Judge:
    return lambda _gt, cand: bool(cand["_predict"])


def test_perfect_judge_has_full_accuracy_and_no_bias() -> None:
    pairs = [_pair("MATCH", True), _pair("NO_MATCH", False), _pair("MATCH", True)]
    m = evaluate_judge(_oracle(), pairs)
    assert m.accuracy == 1.0
    assert m.false_match == 0 and m.false_no_match == 0
    assert m.false_match_rate == 0.0 and m.false_no_match_rate == 0.0


def test_confusion_cells_and_bias_rates() -> None:
    pairs = [
        _pair("MATCH", True),      # true match
        _pair("MATCH", False),     # false no-match (strictness)
        _pair("NO_MATCH", False),  # true no-match
        _pair("NO_MATCH", True),   # false match (leniency)
        _pair("NO_MATCH", True),   # false match (leniency)
    ]
    m = evaluate_judge(_oracle(), pairs)
    assert (m.true_match, m.false_no_match, m.true_no_match, m.false_match) == (1, 1, 1, 2)
    assert m.n == 5
    assert m.accuracy == 2 / 5
    assert m.false_match_rate == 2 / 3      # 2 false matches / 3 expected-NO_MATCH
    assert m.false_no_match_rate == 1 / 2   # 1 false no-match / 2 expected-MATCH


def test_metrics_empty_is_safe() -> None:
    m = evaluate_judge(_oracle(), [])
    assert isinstance(m, JudgeMetrics)
    assert m.n == 0 and m.accuracy == 0.0


_GT = {"file": "a", "lines": "1", "must_mention": ["x"], "description": "d"}


def _sequence_judge(seq: list[bool]) -> Judge:
    """A judge that returns the next bool from `seq` on each call (controlled flakiness)."""
    it = iter(seq)

    def _judge(_gt: dict[str, object], _cand: dict[str, object]) -> bool:
        return next(it)

    return _judge


def test_stability_unanimous_is_one() -> None:
    assert judge_stability(_sequence_judge([True] * 8), _GT, {"title": "c"}, n=8) == 1.0


def test_stability_even_split_is_one_half() -> None:
    flaky = _sequence_judge([True, False, True, False])
    assert judge_stability(flaky, _GT, {"title": "c"}, n=4) == 0.5


def test_stability_majority_agreement() -> None:
    flaky = _sequence_judge([True, True, True, False])  # 3/4 agree on MATCH
    assert judge_stability(flaky, _GT, {"title": "c"}, n=4) == 0.75


# --- gold-set contract (offline) -----------------------------------------


def test_gold_set_loads_and_is_balanced() -> None:
    pairs = load_gold_set()
    assert len(pairs) >= 20
    assert {p.expected for p in pairs} == {"MATCH", "NO_MATCH"}
    n_match = sum(1 for p in pairs if p.expected == "MATCH")
    n_no_match = len(pairs) - n_match
    third = len(pairs) // 3
    assert n_match >= third and n_no_match >= third, "gold-set class balance too skewed"


def test_gold_set_includes_each_adversarial_category() -> None:
    # the judge's value is on the HARD NO_MATCH cases — make sure each is represented
    notes = " ".join(p.note for p in load_gold_set()).lower()
    for marker in ("same-loc-diff-bug", "persuasive-wrong", "vague", "diff-gt"):
        assert marker in notes, f"gold-set missing adversarial category: {marker}"


def test_gold_set_pairs_carry_judge_inputs() -> None:
    for p in load_gold_set():
        assert p.gt.get("must_mention"), f"gt missing must_mention: {p.note}"
        assert p.gt.get("description"), f"gt missing description: {p.note}"
        assert p.candidate.get("title"), f"candidate missing title: {p.note}"
