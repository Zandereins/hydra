"""Case-level scoring — hybrid matcher (deterministic-primary + judge fallback)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from hydra.line_spec import parse_line_spans


@dataclass(frozen=True)
class CaseScore:
    recall: float
    precision: float
    f1: float
    critical_recall: float
    matched: int
    missed: int
    noise: int
    # Distractor-resistance (Track-3 P2): candidates that overlap a benign negative
    # anchor. Defaults keep back-compat for callers/baselines built before P2.
    false_positives: int = 0
    false_positive_rate: float = 0.0


@dataclass(frozen=True)
class FindingMatch:
    ground_truth_idx: int
    candidate_idx: int


RANGE_TOL = 5  # spec §11.4 (was hardcoded 10); calibrate against baseline before freezing

Judge = Callable[[dict[str, object], dict[str, object]], bool]


def _ranges_overlap(a: str, b: str, tol: int = RANGE_TOL) -> bool:
    """True if ANY sub-span of a overlaps ANY sub-span of b (within tol).

    Uses the shared :func:`hydra.line_spec.parse_line_spans` (single source of truth) so
    the matcher and the grounder parse identical grammar. Unparseable specs yield no spans
    -> no overlap.
    """
    a_spans = parse_line_spans(a)
    b_spans = parse_line_spans(b)
    return any(
        not (a2 + tol < b1 or b2 + tol < a1)
        for (a1, a2) in a_spans
        for (b1, b2) in b_spans
    )


def _keyword_match(must_mention: list[str], cand: dict[str, object]) -> bool:
    """True if >=1 must_mention keyword appears in the candidate's text."""
    hay = " ".join(
        str(cand.get(k, "")) for k in ("title", "summary", "message", "evidence")
    ).lower()
    return any(kw.lower() in hay for kw in must_mention)


def _is_match(
    gt: dict[str, object], cand: dict[str, object], judge: Judge | None
) -> bool:
    if gt["file"] != cand.get("file"):
        return False
    if not _ranges_overlap(str(gt["lines"]), str(cand.get("lines", ""))):
        return False
    raw_must = gt.get("must_mention") or []
    must: list[str] = [str(k) for k in raw_must] if isinstance(raw_must, list) else []
    if not must:
        return True  # back-compat: no keywords specified -> file+range is sufficient
    if _keyword_match(must, cand):
        return True
    if judge is not None:  # only the pre-filter-pass / keyword-fail subset reaches the judge
        return bool(judge(gt, cand))
    return False


def _overlaps_any_negative(
    cand: dict[str, object], negative_anchors: list[dict[str, object]]
) -> bool:
    """True if the candidate overlaps any benign negative anchor (file + range)."""
    cand_file = cand.get("file")
    cand_lines = str(cand.get("lines", ""))
    return any(
        na.get("file") == cand_file and _ranges_overlap(str(na.get("lines", "")), cand_lines)
        for na in negative_anchors
    )


def score_case(
    ground_truth: list[dict[str, object]],
    candidates: list[dict[str, object]],
    *,
    judge: Judge | None = None,
    negative_anchors: list[dict[str, object]] | None = None,
) -> CaseScore:
    """Greedy one-to-one matching: file + range-overlap(±5) + (keyword OR judge).

    ``negative_anchors`` (benign distractor locations) drive ``false_positive_rate``:
    a candidate that matched no GT but overlaps a negative anchor is an explicit false
    positive. Matched candidates are never counted as FPs.
    """
    used: set[int] = set()
    matches: list[FindingMatch] = []
    for gi, gt in enumerate(ground_truth):
        for ci, cand in enumerate(candidates):
            if ci in used:
                continue
            if _is_match(gt, cand, judge):
                matches.append(FindingMatch(gi, ci))
                used.add(ci)
                break

    matched = len(matches)
    mandatory = [g for g in ground_truth if g.get("mandatory", False)]
    matched_mandatory = sum(
        1 for m in matches if ground_truth[m.ground_truth_idx].get("mandatory", False)
    )
    recall = matched / max(len(ground_truth), 1)
    precision = matched / max(len(candidates), 1)
    f1 = 2 * recall * precision / max(recall + precision, 1e-9)
    critical_recall = matched_mandatory / max(len(mandatory), 1)

    neg = negative_anchors or []
    false_positives = sum(
        1
        for ci, cand in enumerate(candidates)
        if ci not in used and _overlaps_any_negative(cand, neg)
    )
    false_positive_rate = false_positives / max(len(candidates), 1)

    return CaseScore(
        recall=recall,
        precision=precision,
        f1=f1,
        critical_recall=critical_recall,
        matched=matched,
        missed=len(ground_truth) - matched,
        noise=len(candidates) - matched,
        false_positives=false_positives,
        false_positive_rate=false_positive_rate,
    )
