"""Case-level scoring — hybrid matcher (deterministic-primary + judge fallback)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class CaseScore:
    recall: float
    precision: float
    f1: float
    critical_recall: float
    matched: int
    missed: int
    noise: int


@dataclass(frozen=True)
class FindingMatch:
    ground_truth_idx: int
    candidate_idx: int
    score: float


def _parse_range(lines: str) -> tuple[int, int]:
    if "-" in lines:
        a, b = lines.split("-", 1)
        return int(a), int(b)
    n = int(lines)
    return n, n


RANGE_TOL = 5  # spec §11.4 (was hardcoded 10); calibrate against baseline before freezing

Judge = Callable[[dict[str, object], dict[str, object]], bool]


def _ranges_overlap(a: str, b: str, tol: int = RANGE_TOL) -> bool:
    try:
        a1, a2 = _parse_range(a)
        b1, b2 = _parse_range(b)
    except ValueError:
        return False
    return not (a2 + tol < b1 or b2 + tol < a1)


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


def score_case(
    ground_truth: list[dict[str, object]],
    candidates: list[dict[str, object]],
    *,
    judge: Judge | None = None,
) -> CaseScore:
    """Greedy one-to-one matching: file + range-overlap(±5) + (keyword OR judge)."""
    used: set[int] = set()
    matches: list[FindingMatch] = []
    for gi, gt in enumerate(ground_truth):
        for ci, cand in enumerate(candidates):
            if ci in used:
                continue
            if _is_match(gt, cand, judge):
                matches.append(FindingMatch(gi, ci, 1.0))
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
    return CaseScore(
        recall=recall,
        precision=precision,
        f1=f1,
        critical_recall=critical_recall,
        matched=matched,
        missed=len(ground_truth) - matched,
        noise=len(candidates) - matched,
    )
