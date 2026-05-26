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


_MAX_SPANS = 32  # cap comma-spans so a pathological candidate can't drive O(n*m) overlap


def _parse_ranges(spec: str) -> list[tuple[int, int]]:
    """Parse a line spec into (start, end) pairs.

    Handles single ('15'), range ('13-23'), and comma-separated multi-spans
    ('15,21-22' -> [(15,15),(21,22)]) — real Hydra reports cite all three forms.
    At most _MAX_SPANS spans are parsed (real citations have a handful; the cap
    bounds the matcher against an adversarial mega-spec).
    """
    out: list[tuple[int, int]] = []
    for part in spec.split(",")[:_MAX_SPANS]:
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.append((int(a), int(b)))
        else:
            n = int(part)
            out.append((n, n))
    return out


RANGE_TOL = 5  # spec §11.4 (was hardcoded 10); calibrate against baseline before freezing

Judge = Callable[[dict[str, object], dict[str, object]], bool]


def _ranges_overlap(a: str, b: str, tol: int = RANGE_TOL) -> bool:
    """True if ANY sub-span of a overlaps ANY sub-span of b (within tol)."""
    try:
        a_spans = _parse_ranges(a)
        b_spans = _parse_ranges(b)
    except ValueError:
        return False
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
    return CaseScore(
        recall=recall,
        precision=precision,
        f1=f1,
        critical_recall=critical_recall,
        matched=matched,
        missed=len(ground_truth) - matched,
        noise=len(candidates) - matched,
    )
