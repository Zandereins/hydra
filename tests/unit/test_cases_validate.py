"""Case-data contract for the calibrated multi-finding bench (Track-3 P2).

These tests are the anti-hallucination backstop for hand-authored cases: every
ground-truth finding and negative anchor must validate against the schema AND point at
a real, in-bounds line range of the POST-DIFF workspace (the state `/hydra` actually
reviews). A fabricated file or out-of-range line is caught deterministically here.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from bench.runner.models import GroundTruthFinding, NegativeAnchor
from bench.runner.scoring import _ranges_overlap

CASES_DIR = Path(__file__).resolve().parents[2] / "bench" / "cases"
EXPECTED_CASE_COUNT = 8  # 5 original + 3 new (concurrency/data/api) — spec §3 (n: 5 -> 8)


def _case_dirs() -> list[Path]:
    # STANDARD suite only: isolation-only cases (suite: isolation) have a different contract
    # (single mandatory finding, no submodule) and their own offline tests. Reuse the run_bench
    # discovery so the filter has one source of truth.
    from bench.runner.run_bench import discover_cases

    return [CASES_DIR / name for name in discover_cases()]


def _load_gt(case: Path) -> list[GroundTruthFinding]:
    lines = (case / "expected_findings.jsonl").read_text().splitlines()
    return [GroundTruthFinding.model_validate_json(ln) for ln in lines if ln.strip()]


def _load_na(case: Path) -> list[NegativeAnchor]:
    path = case / "negative_anchors.jsonl"
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    return [NegativeAnchor.model_validate_json(ln) for ln in lines if ln.strip()]


def _bounds(lines: str) -> tuple[int, int]:
    """(min_start, max_end) across all comma/dash sub-spans of a line spec."""
    starts: list[int] = []
    ends: list[int] = []
    for part in str(lines).split(","):
        part = part.strip()
        if not part:
            continue
        a, _, b = part.partition("-")
        starts.append(int(a))
        ends.append(int(b) if b else int(a))
    return min(starts), max(ends)


def test_case_count() -> None:
    assert len(_case_dirs()) == EXPECTED_CASE_COUNT


def test_every_case_ground_truth_validates_and_has_keywords_and_description() -> None:
    for case in _case_dirs():
        rows = _load_gt(case)
        assert rows, f"{case.name} has no ground-truth findings"
        for gt in rows:
            assert gt.must_mention, f"{case.name}: finding missing must_mention"
            assert gt.description, f"{case.name}: finding missing description"


def test_every_case_is_multi_finding_with_mandatory_and_optional() -> None:
    """Multi-finding construct validity (spec §3): 2-4 findings, >=1 mandatory + >=1 optional,
    so recall has real range and critical_recall (mandatory subset) stays the gate metric."""
    for case in _case_dirs():
        rows = _load_gt(case)
        assert 2 <= len(rows) <= 4, f"{case.name}: expected 2-4 GT findings, got {len(rows)}"
        assert any(g.mandatory for g in rows), f"{case.name}: needs >=1 mandatory finding"
        assert any(not g.mandatory for g in rows), f"{case.name}: needs >=1 optional finding"


def test_negative_anchors_validate_and_are_disjoint_from_ground_truth() -> None:
    """A negative anchor must NOT overlap any GT finding in the same case — otherwise a
    real match would be mis-counted as a false positive, corrupting false_positive_rate."""
    for case in _case_dirs():
        gts = _load_gt(case)
        nas = _load_na(case)
        assert nas, f"{case.name}: a calibrated case must ship >=1 negative anchor (distractor)"
        for na in nas:
            assert na.why_benign
            for gt in gts:
                if gt.file == na.file:
                    assert not _ranges_overlap(gt.lines, na.lines), (
                        f"{case.name}: negative anchor {na.file}:{na.lines} overlaps GT "
                        f"{gt.file}:{gt.lines} — a real match would mis-count as an FP"
                    )


@pytest.mark.parametrize("case_dir", _case_dirs(), ids=lambda p: p.name)
def test_anchors_point_at_real_in_bounds_post_diff_lines(case_dir: Path) -> None:
    """Apply the case diff, then assert every GT + negative-anchor citation names a real
    file and a 1<=start<=end<=line_count range in the POST-DIFF tree /hydra reviews."""
    from bench.runner import invoke_hydra_1x

    workspace = invoke_hydra_1x.prepare_case_workspace(case_dir.name)
    try:
        anchors: list[GroundTruthFinding | NegativeAnchor] = [
            *_load_gt(case_dir),
            *_load_na(case_dir),
        ]
        for anchor in anchors:
            target = workspace / anchor.file
            assert target.is_file(), f"{case_dir.name}: {anchor.file!r} missing post-diff"
            n_lines = len(target.read_text().splitlines())
            start, end = _bounds(anchor.lines)
            assert 1 <= start <= end <= n_lines, (
                f"{case_dir.name}: {anchor.file}:{anchor.lines} out of bounds "
                f"(post-diff file has {n_lines} lines)"
            )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
