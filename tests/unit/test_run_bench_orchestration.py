import json
from pathlib import Path

from bench.runner.run_bench import (
    FAST_BENCH_CASES,
    _median_metric_by_case,
    discover_cases,
    gate_against_baseline,
    load_ground_truth,
    plan_runs,
)
from bench.runner.scoring import CaseScore


def _score(f1: float, critical_recall: float = 1.0) -> CaseScore:
    return CaseScore(
        recall=f1, precision=f1, f1=f1, critical_recall=critical_recall,
        matched=1, missed=0, noise=0,
    )


def _multi_run_baseline(cr_by_case: dict[str, float]) -> dict[str, object]:
    # >=2 runs/case so gate_against_baseline treats it as NON single-run (can hard-fail)
    return {
        "cases": {
            c: {"median_critical_recall": cr, "median_f1": 0.5, "runs": [{}, {}, {}]}
            for c, cr in cr_by_case.items()
        }
    }


def test_median_metric_by_case_takes_median_across_runs() -> None:
    runs = [
        {"scores": {"c1": _score(0.4)}},
        {"scores": {"c1": _score(0.6)}},
        {"scores": {"c1": _score(0.5)}},
    ]
    assert _median_metric_by_case(runs, "f1") == {"c1": 0.5}
    assert _median_metric_by_case(runs, "critical_recall") == {"c1": 1.0}


def test_gate_passes_when_no_regression(tmp_path: Path) -> None:
    bl = tmp_path / "baseline.json"
    bl.write_text(json.dumps(_multi_run_baseline({"c1": 1.0, "c2": 1.0})))
    assert gate_against_baseline({"c1": 1.0, "c2": 1.0}, bl) == 0


def test_gate_fails_on_release_regression_against_multi_run_baseline(tmp_path: Path) -> None:
    bl = tmp_path / "baseline.json"
    bl.write_text(json.dumps(_multi_run_baseline({"c1": 1.0, "c2": 1.0})))
    # both cases lose the mandatory finding (crit_recall 1->0) -> release fail -> exit 1
    assert gate_against_baseline({"c1": 0.0, "c2": 0.0}, bl) == 1


def test_gate_returns_2_on_no_scored_runs(tmp_path: Path) -> None:
    # total harness outage (no scored runs) must NOT be reported as a quality regression
    bl = tmp_path / "baseline.json"
    bl.write_text(json.dumps(_multi_run_baseline({"c1": 1.0, "c2": 1.0})))
    assert gate_against_baseline({}, bl) == 2


def test_single_run_baseline_is_advisory_only_never_hard_fails(tmp_path: Path) -> None:
    # A single-run baseline (no/<=1 runs) must NEVER return exit 1, even on a regression.
    bl = tmp_path / "baseline.json"
    bl.write_text(json.dumps({"cases": {
        "c1": {"median_critical_recall": 1.0, "runs": [{}]},
        "c2": {"median_critical_recall": 1.0, "runs": [{}]},
    }}))
    assert gate_against_baseline({"c1": 0.0, "c2": 0.0}, bl) == 0  # advisory, despite regression


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
