"""Key-gated: measure the REAL judge against the gold-set (Track-3 P4, spec §5/§10).

Skipped without ANTHROPIC_API_KEY (no cost in normal CI). When run, it asserts the
judge clears an accuracy floor and prints its leniency/strictness bias + a stability
sample for human inspection — these numbers are what calibrate the gate's trust in
judge-decided matches.
"""
from __future__ import annotations

import os

import pytest

ACCURACY_FLOOR = 0.80          # judge must classify >=80% of the gold-set correctly
STABILITY_FLOOR = 0.80         # temperature=0 must agree >=4/5 on a clear-cut pair
_HAS_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))


@pytest.mark.skipif(not _HAS_KEY, reason="no ANTHROPIC_API_KEY — live judge call")
def test_real_judge_accuracy_and_bias_on_gold_set() -> None:
    from anthropic import Anthropic

    from bench.runner.judge import make_judge
    from bench.runner.judge_eval import evaluate_judge, load_gold_set

    model = os.environ.get("HYDRA_JUDGE_MODEL", "claude-haiku-4-5-20251001")
    judge = make_judge(client=Anthropic(), model=model)
    m = evaluate_judge(judge, load_gold_set())
    print(
        f"[judge-gold] n={m.n} accuracy={m.accuracy:.3f} "
        f"leniency(false_match_rate)={m.false_match_rate:.3f} "
        f"strictness(false_no_match_rate)={m.false_no_match_rate:.3f} "
        f"confusion(tm={m.true_match},tnm={m.true_no_match},fm={m.false_match},fnm={m.false_no_match})"
    )
    assert m.accuracy >= ACCURACY_FLOOR, f"judge accuracy {m.accuracy:.3f} < {ACCURACY_FLOOR}"


@pytest.mark.skipif(not _HAS_KEY, reason="no ANTHROPIC_API_KEY — live judge call")
def test_real_judge_stability_on_clear_pair() -> None:
    from anthropic import Anthropic

    from bench.runner.judge import make_judge
    from bench.runner.judge_eval import judge_stability, load_gold_set

    model = os.environ.get("HYDRA_JUDGE_MODEL", "claude-haiku-4-5-20251001")
    judge = make_judge(client=Anthropic(), model=model)
    clear = next(p for p in load_gold_set() if p.expected == "MATCH" and "exact" in p.note)
    rate = judge_stability(judge, clear.gt, clear.candidate, n=5)
    print(f"[judge-gold] stability(clear MATCH pair, n=5)={rate:.2f}")
    assert rate >= STABILITY_FLOOR, f"judge stability {rate:.2f} < {STABILITY_FLOOR} (clear pair)"
