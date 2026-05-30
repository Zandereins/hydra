import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

import bench.runner.extract_findings as _ef
import bench.runner.invoke_hydra_1x as _inv
import bench.runner.run_bench as _rb
from bench.runner.run_bench import (
    FAST_BENCH_CASES,
    MAX_ATTEMPTS,
    _capture_case_run,
    _median_metric_by_case,
    _print_telemetry,
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


def _sequence(*behaviors: object):
    """A stateful mock: each call returns/raises the next behavior in order.
    A BaseException instance is raised; anything else is returned."""
    state = {"i": 0}

    def fn(*_a: object, **_k: object) -> Any:
        b = behaviors[state["i"]]
        state["i"] += 1
        if isinstance(b, BaseException):
            raise b
        return b

    return fn


def _patch_capture(
    monkeypatch: pytest.MonkeyPatch,
    *,
    invoke: object,
    extract: object,
    score: object | None = None,
) -> None:
    # _capture_case_run imports prepare_case_workspace/invoke_hydra/extract_candidates
    # INSIDE the function -> patch the source modules so the fresh import binds the mocks.
    monkeypatch.setattr(_inv, "prepare_case_workspace", lambda _cid: Path("/tmp/hydra-ws-fake"))
    monkeypatch.setattr(_inv, "invoke_hydra", invoke)
    monkeypatch.setattr(_ef, "extract_candidates", extract)
    monkeypatch.setattr(_rb, "load_ground_truth", lambda _cid: [])
    monkeypatch.setattr(_rb, "load_negative_anchors", lambda _cid: [])
    if score is not None:
        monkeypatch.setattr(_rb, "score_case", score)


_TIMEOUT = subprocess.TimeoutExpired(cmd="claude", timeout=1)
_NONZERO = subprocess.CalledProcessError(returncode=1, cmd="claude")
_CANDS = [{"file": "a.ts", "lines": "1", "title": "t"}]


def test_capture_case_run_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    sc = _score(0.5)
    _patch_capture(
        monkeypatch,
        invoke=lambda *_a: Path("r.md"),
        extract=lambda *_a: _CANDS,
        score=lambda *_a, **_k: sc,
    )
    score, outcomes = _capture_case_run("c", judge=None)
    assert score is sc
    assert outcomes == ["scored"]


def test_capture_case_run_capture_all_keeps_recall_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    # capture-all: a scorable report with recall 0 is a quality data point, NOT discarded.
    miss = _score(0.0, critical_recall=0.0)
    _patch_capture(
        monkeypatch, invoke=lambda *_a: Path("r.md"), extract=lambda *_a: _CANDS,
        score=lambda *_a, **_k: miss,
    )
    score, outcomes = _capture_case_run("c", judge=None)
    assert score is miss and outcomes == ["scored"]


def test_capture_case_run_retries_timeout_then_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    sc = _score(1.0)
    _patch_capture(
        monkeypatch, invoke=_sequence(_TIMEOUT, Path("r.md")), extract=lambda *_a: _CANDS,
        score=lambda *_a, **_k: sc,
    )
    score, outcomes = _capture_case_run("c", judge=None)
    assert score is sc and outcomes == ["timeout", "scored"]


def test_capture_case_run_nonzero_exit_is_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    # a non-zero `claude` exit (rate limit) must NOT abort — it's a retryable invoke_error.
    sc = _score(1.0)
    _patch_capture(
        monkeypatch, invoke=_sequence(_NONZERO, Path("r.md")), extract=lambda *_a: _CANDS,
        score=lambda *_a, **_k: sc,
    )
    score, outcomes = _capture_case_run("c", judge=None)
    assert score is sc and outcomes == ["invoke_error", "scored"]


def test_capture_case_run_no_report_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    sc = _score(1.0)
    _patch_capture(
        monkeypatch, invoke=_sequence(RuntimeError("no report"), Path("r.md")),
        extract=lambda *_a: _CANDS, score=lambda *_a, **_k: sc,
    )
    score, outcomes = _capture_case_run("c", judge=None)
    assert score is sc and outcomes == ["no_report", "scored"]


def test_capture_case_run_action_less_then_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    # a report with zero extractable findings is headless degradation -> retried.
    sc = _score(1.0)
    _patch_capture(
        monkeypatch, invoke=lambda *_a: Path("r.md"), extract=_sequence([], _CANDS),
        score=lambda *_a, **_k: sc,
    )
    score, outcomes = _capture_case_run("c", judge=None)
    assert score is sc and outcomes == ["action_less", "scored"]


def test_capture_case_run_all_attempts_fail_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_capture(
        monkeypatch, invoke=_sequence(*([_TIMEOUT] * MAX_ATTEMPTS)), extract=lambda *_a: _CANDS,
    )
    score, outcomes = _capture_case_run("c", judge=None)
    assert score is None  # harness outage -> absent from the gate, never a fabricated 0
    assert outcomes == ["timeout"] * MAX_ATTEMPTS


def test_capture_case_run_cleans_workspace_each_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(shutil, "rmtree", lambda ws, **_k: calls.append(ws))
    _patch_capture(
        monkeypatch, invoke=lambda *_a: Path("r.md"), extract=lambda *_a: _CANDS,
        score=lambda *_a, **_k: _score(1.0),
    )
    _capture_case_run("c", judge=None)
    assert len(calls) == 1  # finally: workspace removed even on the scoring (success) path


def test_print_telemetry_summary(capsys: pytest.CaptureFixture[str]) -> None:
    telemetry = [
        {"case": "c1", "attempts": 2, "outcomes": ["timeout", "scored"], "accepted": True},
        {"case": "c2", "attempts": 5, "outcomes": ["timeout"] * 5, "accepted": False},
    ]
    _print_telemetry(telemetry)
    out = capsys.readouterr().out
    assert "slots=2" in out and "scored=1" in out and "total_attempts=7" in out


def test_print_telemetry_per_case_success_rate(capsys: pytest.CaptureFixture[str]) -> None:
    telemetry = [{"case": "c1", "attempts": 2, "outcomes": ["timeout", "scored"], "accepted": True}]
    per_case = {"c1": {"outcomes": ["timeout", "scored"]}}
    _print_telemetry(telemetry, per_case)
    out = capsys.readouterr().out
    assert "c1: success_rate=" in out


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


def test_discover_cases_finds_all_eight():
    cases = discover_cases()
    assert len(cases) == 8  # 5 original + 3 new (concurrency/data/api) — Track-3 P2
    assert "01-axios-header-injection" in cases


def test_fast_bench_is_two_cases_one_run():
    runs = plan_runs(mode="fast")
    assert sorted({r.case_id for r in runs}) == sorted(FAST_BENCH_CASES)
    assert all(r.runs == 1 and r.hydra_mode == "standard" for r in runs)


def test_full_bench_is_eight_cases_standard_and_deep_three_runs():
    runs = plan_runs(mode="full")
    assert len({r.case_id for r in runs}) == 8
    modes = {(r.case_id, r.hydra_mode) for r in runs}
    assert len(modes) == 16  # 8 cases x {standard, deep}
    assert all(r.runs == 3 for r in runs)


def test_calibrate_mode_is_all_cases_standard_n_runs():
    # P6 capture mode: every case, standard mode, RUNS_PER_CASE scored slots for the CI baseline
    from bench.runner.run_bench import RUNS_PER_CASE

    runs = plan_runs(mode="calibrate")
    assert len({r.case_id for r in runs}) == 8
    assert all(r.hydra_mode == "standard" for r in runs)
    assert all(r.runs == RUNS_PER_CASE for r in runs)
    assert RUNS_PER_CASE >= 5  # N≈5 for bootstrap CIs (spec §4)
