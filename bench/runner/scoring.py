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


def _max_bipartite_matching(adjacency: list[list[int]]) -> dict[int, int]:
    """Maximum-cardinality one-to-one matching via Kuhn's augmenting-path algorithm.

    ``adjacency[gi]`` lists the candidate indices that match ground-truth ``gi``. Returns
    ``{candidate_idx: ground_truth_idx}``. Greedy (first free candidate per GT in order)
    under-counts when GT ranges overlap: an early GT can claim the only candidate a later
    GT needed. Augmenting paths reassign such conflicts to reach the true maximum, so recall
    is never under-attributed on overlapping intra-case ranges (cases 01/05/07/08).
    """
    match_for_cand: dict[int, int] = {}

    def augment(gi: int, seen: set[int]) -> bool:
        for ci in adjacency[gi]:
            if ci in seen:
                continue
            seen.add(ci)
            if ci not in match_for_cand or augment(match_for_cand[ci], seen):
                match_for_cand[ci] = gi
                return True
        return False

    for gi in range(len(adjacency)):
        augment(gi, set())
    return match_for_cand


def score_case(
    ground_truth: list[dict[str, object]],
    candidates: list[dict[str, object]],
    *,
    judge: Judge | None = None,
    negative_anchors: list[dict[str, object]] | None = None,
) -> CaseScore:
    """Optimal one-to-one matching: file + range-overlap(±5) + (keyword OR judge).

    Edges are computed once (one ``_is_match`` per GT/candidate pair, so the judge is asked
    at most once per pair — deterministic), then matched with maximum-cardinality bipartite
    matching so overlapping GT ranges never misattribute recall.

    ``negative_anchors`` (benign distractor locations) drive ``false_positive_rate``:
    a candidate that matched no GT but overlaps a negative anchor is an explicit false
    positive. Matched candidates are never counted as FPs.
    """
    adjacency = [
        [ci for ci, cand in enumerate(candidates) if _is_match(gt, cand, judge)]
        for gt in ground_truth
    ]
    match_for_cand = _max_bipartite_matching(adjacency)
    used: set[int] = set(match_for_cand)
    matches = [FindingMatch(gi, ci) for ci, gi in match_for_cand.items()]

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
    unmatched = [cand for ci, cand in enumerate(candidates) if ci not in used]
    # false_positives: raw count of unmatched candidates that landed on a benign distractor.
    false_positives = sum(1 for cand in unmatched if _overlaps_any_negative(cand, neg))
    # false_positive_rate: share of KNOWN distractors the model was fooled into flagging.
    # Denominator is the anchor count, not the candidate count, so a precise model (few
    # candidates) is never penalised harder than a noisy one for the same distractor hit.
    flagged_negatives = sum(
        1 for na in neg if any(_overlaps_any_negative(cand, [na]) for cand in unmatched)
    )
    false_positive_rate = flagged_negatives / max(len(neg), 1)

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
