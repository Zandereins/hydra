"""Judge calibration: gold-set accuracy/bias + stability (Track-3 P4, spec §5).

The LLM judge adjudicates the pre-filter-pass / keyword-fail subset. Before trusting it
we measure it against a hand-labeled gold-set (accuracy + leniency/strictness bias) and
quantify its run-to-run nondeterminism (temperature=0 != deterministic). Pure functions
over a `Judge` callable, so the harness is mock-testable; the real judge is exercised
only by a key-gated integration test.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from bench.runner.scoring import Judge

GOLD_SET_PATH = Path(__file__).resolve().parents[2] / "bench" / "judge_gold.jsonl"


class GoldPair(BaseModel):
    """One hand-labeled judge case: a ground-truth bug + a candidate + the expected
    verdict. `note` records WHY (adversarial near-miss / paraphrase / vague / etc.)."""

    model_config = ConfigDict(extra="forbid")

    gt: dict[str, Any]
    candidate: dict[str, Any]
    expected: Literal["MATCH", "NO_MATCH"]
    note: str = ""


def load_gold_set(path: Path = GOLD_SET_PATH) -> list[GoldPair]:
    """Load + validate the judge gold-set (one GoldPair JSON per line)."""
    return [
        GoldPair.model_validate_json(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


@dataclass(frozen=True)
class JudgeMetrics:
    n: int
    accuracy: float
    true_match: int       # expected MATCH, judged MATCH
    true_no_match: int    # expected NO_MATCH, judged NO_MATCH
    false_match: int      # expected NO_MATCH, judged MATCH  (leniency error)
    false_no_match: int   # expected MATCH, judged NO_MATCH  (strictness error)
    false_match_rate: float     # leniency bias: false_match / expected-NO_MATCH
    false_no_match_rate: float  # strictness bias: false_no_match / expected-MATCH


def evaluate_judge(judge: Judge, pairs: list[GoldPair]) -> JudgeMetrics:
    """Run the judge over the gold-set; return accuracy + the full confusion matrix and
    the two directional bias rates (leniency = false MATCH, strictness = false NO_MATCH)."""
    tm = tnm = fm = fnm = 0
    for p in pairs:
        predicted_match = bool(judge(p.gt, p.candidate))
        expected_match = p.expected == "MATCH"
        if expected_match and predicted_match:
            tm += 1
        elif not expected_match and not predicted_match:
            tnm += 1
        elif not expected_match and predicted_match:
            fm += 1
        else:
            fnm += 1
    n = len(pairs)
    n_pos = sum(1 for p in pairs if p.expected == "MATCH")
    n_neg = n - n_pos
    return JudgeMetrics(
        n=n,
        accuracy=(tm + tnm) / n if n else 0.0,
        true_match=tm,
        true_no_match=tnm,
        false_match=fm,
        false_no_match=fnm,
        false_match_rate=fm / n_neg if n_neg else 0.0,
        false_no_match_rate=fnm / n_pos if n_pos else 0.0,
    )


def judge_stability(
    judge: Judge, gt: dict[str, Any], candidate: dict[str, Any], *, n: int = 10
) -> float:
    """Run the judge n times on one (gt, candidate) pair; return the agreement rate =
    fraction landing on the majority verdict (1.0 = fully deterministic, 0.5 = coin flip).
    Quantifies temperature=0 nondeterminism (spec §5)."""
    if n <= 0:
        return 1.0
    matches = sum(1 for _ in range(n) if bool(judge(gt, candidate)))
    return max(matches, n - matches) / n
