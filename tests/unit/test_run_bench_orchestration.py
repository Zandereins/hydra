import json
from pathlib import Path

from bench.runner.run_bench import (
    FAST_BENCH_CASES,
    _median_f1_by_case,
    discover_cases,
    gate_against_baseline,
    load_ground_truth,
    plan_runs,
)
from bench.runner.scoring import CaseScore


def _score(f1: float) -> CaseScore:
    return CaseScore(
        recall=f1, precision=f1, f1=f1, critical_recall=f1, matched=1, missed=0, noise=0
    )


def test_median_f1_by_case_takes_median_across_runs() -> None:
    runs = [
        {"scores": {"c1": _score(0.4)}},
        {"scores": {"c1": _score(0.6)}},
        {"scores": {"c1": _score(0.5)}},
    ]
    assert _median_f1_by_case(runs) == {"c1": 0.5}


def test_gate_passes_when_no_regression(tmp_path: Path, capsys) -> None:
    bl = tmp_path / "baseline.json"
    bl.write_text(json.dumps({"cases": {"c1": {"median_f1": 0.5}, "c2": {"median_f1": 0.5}}}))
    assert gate_against_baseline({"c1": 0.5, "c2": 0.5}, bl) == 0


def test_gate_fails_on_release_regression(tmp_path: Path, capsys) -> None:
    bl = tmp_path / "baseline.json"
    bl.write_text(json.dumps({"cases": {"c1": {"median_f1": 0.8}, "c2": {"median_f1": 0.8}}}))
    # both cases drop >=10pp -> release fail -> exit code 1
    assert gate_against_baseline({"c1": 0.6, "c2": 0.6}, bl) == 1


def test_load_ground_truth_validates_and_carries_keywords():
    # load_ground_truth must go through GroundTruthFinding (must_mention enforced)
    rows = load_ground_truth("01-axios-header-injection")
    assert rows
    for row in rows:
        assert row["must_mention"], "validated ground truth must carry >=1 keyword"


def test_discover_cases_finds_all_five():
    cases = discover_cases()
    assert len(cases) == 5
    assert "01-axios-header-injection" in cases


def test_fast_bench_is_two_cases_one_run():
    runs = plan_runs(mode="fast")
    assert sorted({r.case_id for r in runs}) == sorted(FAST_BENCH_CASES)
    assert all(r.runs == 1 and r.hydra_mode == "standard" for r in runs)


def test_full_bench_is_five_cases_standard_and_deep_three_runs():
    runs = plan_runs(mode="full")
    assert len({r.case_id for r in runs}) == 5
    modes = {(r.case_id, r.hydra_mode) for r in runs}
    assert len(modes) == 10  # 5 cases x {standard, deep}
    assert all(r.runs == 3 for r in runs)
