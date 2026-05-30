"""Calibrate CITATION_THRESHOLD via a TP/FP sweep + a hallucination primitive (P5, spec §6).

The grounder flags a finding CITATION_PRESENT when the fraction of its salient tokens
appearing at the cited lines clears CITATION_THRESHOLD (was an uncalibrated 0.4). Here a
hand-labeled set of (claim, cited-snippet, grounded|hallucinated) pairs is swept over
candidate thresholds; the value maximizing grounding-F1 is chosen, frozen into
``hydra.grounding.CITATION_THRESHOLD`` and re-derived by a test (reproducible).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from hydra.grounding import count_present, salient_tokens_from_text

LABELS_PATH = Path(__file__).resolve().parents[2] / "bench" / "grounding_labels.jsonl"
DEFAULT_CANDIDATES = tuple(round(0.05 * i, 2) for i in range(1, 20))  # 0.05 .. 0.95


class GroundingLabel(BaseModel):
    """One labelled citation: the finding's claim text + the cited source snippet +
    whether the citation genuinely grounds (grounded) or is a hallucination."""

    model_config = ConfigDict(extra="forbid")

    claim: str
    snippet: str
    label: Literal["grounded", "hallucinated"]
    lines: str = ""  # informational (which lines the snippet came from)
    note: str = ""


def load_grounding_labels(path: Path = LABELS_PATH) -> list[GroundingLabel]:
    return [
        GroundingLabel.model_validate_json(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def citation_ratio(claim: str, snippet: str) -> float:
    """Fraction of the claim's salient tokens present (as whole words) in the snippet —
    the exact quantity ``hydra.grounding.ground_finding`` thresholds on."""
    tokens = salient_tokens_from_text(claim)
    return count_present(tokens, snippet) / max(len(tokens), 1)


def is_likely_hallucination(claim: str, snippet: str, *, threshold: float) -> bool:
    """A candidate whose cited snippet fails to ground its claim is a likely
    hallucination (spec §6 — Pillar A tied into the bench as a quality axis)."""
    return citation_ratio(claim, snippet) < threshold


@dataclass(frozen=True)
class SweepResult:
    best_threshold: float
    best_f1: float
    table: list[tuple[float, float]]  # (threshold, grounding-F1)


def _f1_at(scored: list[tuple[float, bool]], threshold: float) -> float:
    """Grounding-F1 of the 'predict grounded when ratio>=threshold' classifier
    (positive class = genuinely grounded)."""
    tp = sum(1 for r, grounded in scored if r >= threshold and grounded)
    fp = sum(1 for r, grounded in scored if r >= threshold and not grounded)
    fn = sum(1 for r, grounded in scored if r < threshold and grounded)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0


def sweep_over_ratios(
    scored: list[tuple[float, bool]], *, candidates: list[float] | tuple[float, ...]
) -> SweepResult:
    """Sweep candidate thresholds over pre-scored (ratio, is_grounded) pairs; pick the
    F1-maximizing threshold. On a plateau of equal best F1, choose the median threshold
    (most robust separation)."""
    table = [(t, _f1_at(scored, t)) for t in candidates]
    best_f1 = max((f1 for _, f1 in table), default=0.0)
    plateau = [t for t, f1 in table if abs(f1 - best_f1) < 1e-9]
    # round to kill float-median artifacts (0.3249999..) so the frozen threshold is exact
    best_threshold = round(float(statistics.median(plateau)), 4) if plateau else 0.0
    return SweepResult(best_threshold=best_threshold, best_f1=best_f1, table=table)


def sweep_threshold(
    labels: list[GroundingLabel],
    *,
    candidates: list[float] | tuple[float, ...] = DEFAULT_CANDIDATES,
) -> SweepResult:
    """Compute each label's citation ratio, then sweep for the F1-maximizing threshold."""
    scored = [(citation_ratio(ln.claim, ln.snippet), ln.label == "grounded") for ln in labels]
    return sweep_over_ratios(scored, candidates=candidates)
