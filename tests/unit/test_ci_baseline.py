"""CI baseline writer + blocking CI gate wiring (Track-3 P3b, spec §4)."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

import bench.runner.extract_findings as extract_findings
import bench.runner.invoke_hydra_1x as invoke_hydra_1x
import bench.runner.run_bench as run_bench
from bench.runner.run_bench import (
    aggregate_outcomes,
    gate_against_ci_baseline,
    load_baseline_cases,
    metric_cis,
    write_ci_baseline,
)
from bench.runner.scoring import CaseScore
from bench.runner.stats import MetricCI


def _score(cr: float, recall: float = 1.0, fpr: float = 0.0) -> CaseScore:
    return CaseScore(
        recall=recall, precision=0.5, f1=0.5, critical_recall=cr,
        matched=1, missed=0, noise=1, false_positives=0, false_positive_rate=fpr,
    )


# --- aggregate_outcomes ---------------------------------------------------


def test_aggregate_outcomes_counts_scored_and_failures() -> None:
    n_attempts, n_scored, failure_modes = aggregate_outcomes(
        ["timeout", "no_report", "scored", "action_less", "scored"]
    )
    assert n_attempts == 5
    assert n_scored == 2
    assert failure_modes == {"timeout": 1, "no_report": 1, "action_less": 1}


def test_aggregate_outcomes_all_scored_has_no_failures() -> None:
    n_attempts, n_scored, failure_modes = aggregate_outcomes(["scored", "scored"])
    assert (n_attempts, n_scored, failure_modes) == (2, 2, {})


# --- metric_cis -----------------------------------------------------------


def test_metric_cis_covers_all_gate_metrics() -> None:
    cis = metric_cis([_score(1.0), _score(1.0), _score(1.0)])
    assert set(cis) == {"critical_recall", "recall", "f1", "false_positive_rate"}


def test_metric_cis_uses_wilson_for_binary_critical_recall() -> None:
    # critical_recall is the gated, binary metric (1 mandatory finding/case): it must use
    # the Wilson proportion CI, not bootstrap-of-median. 3/3 caught -> point 1.0 but the
    # honest lower bound is < 1.0 (small N), so the gate is not blind (roadmap 0.1).
    cr = metric_cis([_score(1.0), _score(1.0), _score(1.0)])["critical_recall"]
    assert cr.median == 1.0
    assert cr.ci_high == 1.0
    assert cr.ci_low < 1.0
    # a flaky miss (2/3) stays a proper proportion CI, never the degenerate [0, 1]
    cr2 = metric_cis([_score(1.0), _score(0.0), _score(1.0)])["critical_recall"]
    assert cr2.median == 2 / 3
    assert cr2.ci_low > 0.0


# --- write_ci_baseline ----------------------------------------------------


def test_write_ci_baseline_schema_and_success_rate(tmp_path: Path) -> None:
    out = tmp_path / "baseline.json"
    write_ci_baseline(
        label="hydra-1.x-ci",
        commit_sha="abc123",
        per_case={
            "01-case": {
                "scores": [_score(1.0), _score(1.0), _score(0.0), _score(1.0), _score(1.0)],
                "outcomes": ["scored", "scored", "timeout", "scored", "scored", "scored"],
            }
        },
        output_path=out,
    )
    payload = json.loads(out.read_text())
    assert payload["statistical"] is True
    case = payload["cases"]["01-case"]
    assert case["n_attempts"] == 6
    assert case["n_scored"] == 5
    assert abs(case["success_rate"] - 5 / 6) < 1e-9
    assert case["failure_modes"] == {"timeout": 1}
    cr = case["metrics"]["critical_recall"]
    assert {"median", "ci_low", "ci_high"} <= set(cr)
    assert cr["ci_low"] <= cr["median"] <= cr["ci_high"]


# --- gate_against_ci_baseline ---------------------------------------------


def _ci_baseline(tmp_path: Path, crit_by_case: dict[str, tuple[float, float]]) -> Path:
    """Write a minimal statistical baseline with critical_recall CIs per case."""
    out = tmp_path / "ci-baseline.json"
    out.write_text(json.dumps({
        "statistical": True,
        "cases": {
            case: {"metrics": {"critical_recall": {
                "median": (lo + hi) / 2, "ci_low": lo, "ci_high": hi}}}
            for case, (lo, hi) in crit_by_case.items()
        },
    }))
    return out


def test_ci_gate_passes_on_overlapping_cis(tmp_path: Path) -> None:
    bl = _ci_baseline(tmp_path, {"c1": (0.8, 1.0), "c2": (0.8, 1.0)})
    current = {"c1": MetricCI(0.9, 0.75, 1.0), "c2": MetricCI(0.9, 0.7, 1.0)}
    assert gate_against_ci_baseline(current, bl) == 0


def test_ci_gate_fails_when_two_cases_disjoint_below(tmp_path: Path) -> None:
    bl = _ci_baseline(tmp_path, {"c1": (0.8, 1.0), "c2": (0.8, 1.0)})
    current = {"c1": MetricCI(0.1, 0.0, 0.3), "c2": MetricCI(0.2, 0.1, 0.4)}
    assert gate_against_ci_baseline(current, bl) == 1


def test_ci_gate_returns_2_on_no_current_data(tmp_path: Path) -> None:
    bl = _ci_baseline(tmp_path, {"c1": (0.8, 1.0), "c2": (0.8, 1.0)})
    assert gate_against_ci_baseline({}, bl) == 2


# --- _capture_case_run: capture-all, no selection bias (roadmap 0.2) -------


def _wire_capture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    invocations: list[object],
    extractions: list[list[dict[str, object]]],
) -> None:
    """Drive _capture_case_run's collaborators from scripted per-attempt sequences.

    ``invocations[i]`` is either a report Path or an Exception to raise on attempt i;
    ``extractions[i]`` is the candidate list extract_candidates returns. score_case is
    stubbed to derive recall from candidate count (a non-empty report that misses the GT
    still scores recall=0 — the data point the old code wrongly discarded)."""
    inv_iter = iter(invocations)
    ext_iter = iter(extractions)

    def fake_invoke(workspace: Path) -> Path:
        item = next(inv_iter)
        if isinstance(item, Exception):
            raise item
        return tmp_path / "report.md"

    def fake_extract(report_path: Path) -> list[dict[str, object]]:
        return next(ext_iter)

    def fake_score(
        gt: list[dict[str, object]], cands: list[dict[str, object]], **_: object
    ) -> CaseScore:
        # a report with candidates that miss the GT scores recall=0 (genuine miss);
        # an empty report scores recall=0 too — the discriminator is candidate count.
        return _score(1.0, recall=0.5) if cands else _score(0.0, recall=0.0)

    monkeypatch.setattr(invoke_hydra_1x, "prepare_case_workspace", lambda case_id: tmp_path)
    monkeypatch.setattr(invoke_hydra_1x, "invoke_hydra", fake_invoke)
    monkeypatch.setattr(extract_findings, "extract_candidates", fake_extract)
    monkeypatch.setattr(run_bench, "score_case", fake_score)
    monkeypatch.setattr(run_bench, "load_ground_truth", lambda case_id: [])
    monkeypatch.setattr(run_bench, "load_negative_anchors", lambda case_id: [])


def test_capture_keeps_a_scored_run_even_with_zero_recall(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The bug: a report WITH findings that miss the GT (recall=0) is a real quality
    # data point; the old code retried it away, biasing the baseline upward. It must be
    # accepted on the first scored attempt.
    # Script enough attempts that the OLD (buggy) code, which retries every recall=0 run,
    # exhausts them and we see ["action_less"]*N — a clean assertion failure, not an error.
    _wire_capture(
        monkeypatch, tmp_path,
        invocations=[tmp_path] * run_bench.MAX_ATTEMPTS,
        extractions=[[{"file": "a.js", "lines": "1"}]] * run_bench.MAX_ATTEMPTS,
    )
    # A report with candidates that all miss the GT scores recall=0 — the data point the
    # old code discarded. Force that regardless of candidate count:
    monkeypatch.setattr(run_bench, "score_case", lambda gt, c, **k: _score(0.0, recall=0.0))
    score, outcomes = run_bench._capture_case_run("c", judge=None)
    assert score is not None
    assert score.recall == 0.0
    assert outcomes == ["scored"]  # accepted immediately, NOT retried away


def test_capture_retries_empty_report_as_harness_degradation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # An empty/action-less report (0 candidates) is documented headless degradation, not
    # a quality signal -> retried; the first report WITH findings is then kept.
    _wire_capture(
        monkeypatch, tmp_path,
        invocations=[tmp_path, tmp_path],
        extractions=[[], [{"file": "a.js", "lines": "1"}]],
    )
    score, outcomes = run_bench._capture_case_run("c", judge=None)
    assert score is not None and score.recall == 0.5
    assert outcomes == ["action_less", "scored"]


def test_capture_returns_none_when_every_attempt_degrades(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # All MAX_ATTEMPTS produce empty reports -> no quality data point; return None so the
    # case is absent from the gate (harness outage), never a fabricated recall=0 score.
    _wire_capture(
        monkeypatch, tmp_path,
        invocations=[tmp_path] * run_bench.MAX_ATTEMPTS,
        extractions=[[]] * run_bench.MAX_ATTEMPTS,
    )
    score, outcomes = run_bench._capture_case_run("c", judge=None)
    assert score is None
    assert outcomes == ["action_less"] * run_bench.MAX_ATTEMPTS


def test_capture_retries_transient_failures_then_scores(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # timeout + no-report are transient infra failures -> retried + recorded for the
    # success-rate telemetry, then the first scored run is accepted.
    _wire_capture(
        monkeypatch, tmp_path,
        invocations=[
            subprocess.TimeoutExpired(cmd="claude", timeout=1),
            RuntimeError("no report produced"),
            tmp_path,
        ],
        extractions=[[{"file": "a.js", "lines": "1"}]],
    )
    score, outcomes = run_bench._capture_case_run("c", judge=None)
    assert score is not None and score.recall == 0.5
    assert outcomes == ["timeout", "no_report", "scored"]


def test_capture_retries_non_zero_claude_exit_not_crashes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A non-zero `claude --print` exit (rate limit / transient) raised CalledProcessError,
    # which _capture_case_run did NOT catch -> it aborted the entire multi-hour capture with
    # no baseline written. It must instead be a retryable harness failure.
    _wire_capture(
        monkeypatch, tmp_path,
        invocations=[subprocess.CalledProcessError(1, "claude"), tmp_path],
        extractions=[[{"file": "a.js", "lines": "1"}]],
    )
    score, outcomes = run_bench._capture_case_run("c", judge=None)
    assert score is not None and score.recall == 0.5
    assert outcomes == ["invoke_error", "scored"]


def test_capture_returns_none_when_every_invocation_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A sustained outage (e.g. the plan rate limit) where every attempt exits non-zero must
    # yield None (case absent from the gate = honest outage), never crash the run.
    _wire_capture(
        monkeypatch, tmp_path,
        invocations=[subprocess.CalledProcessError(1, "claude")] * run_bench.MAX_ATTEMPTS,
        extractions=[],
    )
    score, outcomes = run_bench._capture_case_run("c", judge=None)
    assert score is None
    assert outcomes == ["invoke_error"] * run_bench.MAX_ATTEMPTS


# --- incremental persistence + resume (crash/rate-limit safety) ------------


def test_load_baseline_cases_missing_returns_empty(tmp_path: Path) -> None:
    assert load_baseline_cases(tmp_path / "nope.json") == {}


def test_load_baseline_cases_reads_cases(tmp_path: Path) -> None:
    out = tmp_path / "bl.json"
    write_ci_baseline("l", "sha", {"01": {"scores": [_score(1.0)], "outcomes": ["scored"]}}, out)
    cases = load_baseline_cases(out)
    assert set(cases) == {"01"}
    assert cases["01"]["n_scored"] == 1


def test_write_ci_baseline_merges_prior_cases(tmp_path: Path) -> None:
    out = tmp_path / "bl.json"
    prior = {"01-done": {"n_attempts": 5, "n_scored": 5, "success_rate": 1.0,
                         "failure_modes": {}, "metrics": {}}}
    write_ci_baseline(
        "l", "sha", {"02-new": {"scores": [_score(1.0)], "outcomes": ["scored"]}}, out,
        prior_cases=prior,
    )
    cases = json.loads(out.read_text())["cases"]
    assert set(cases) == {"01-done", "02-new"}  # prior kept + new added


def test_write_ci_baseline_new_overrides_prior_partial(tmp_path: Path) -> None:
    out = tmp_path / "bl.json"
    prior = {"01": {"n_scored": 2}}  # a partial prior entry
    write_ci_baseline(
        "l", "sha",
        {"01": {"scores": [_score(1.0)] * 5, "outcomes": ["scored"] * 5}}, out,
        prior_cases=prior,
    )
    cases = json.loads(out.read_text())["cases"]
    assert cases["01"]["n_scored"] == 5  # recaptured fresh entry wins over prior partial


def test_run_mode_persists_each_case_so_a_crash_keeps_prior_cases(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Incremental persistence: caseA is written to disk BEFORE caseB is attempted, so a crash
    # (or rate-limit/kill) during caseB never loses caseA — the run is resumable.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("JUDGE_ENABLED", "0")
    monkeypatch.setattr(run_bench, "plan_runs", lambda *, mode: [
        run_bench.RunSpec("caseA", "standard", 1),
        run_bench.RunSpec("caseB", "standard", 1),
    ])

    def fake_capture(case_id: str, judge: object) -> tuple[CaseScore | None, list[str]]:
        if case_id == "caseB":
            raise RuntimeError("simulated crash mid-capture")
        return _score(1.0), ["scored"]

    monkeypatch.setattr(run_bench, "_capture_case_run", fake_capture)
    out = tmp_path / "bl.json"
    with pytest.raises(RuntimeError):
        run_bench._run_mode("calibrate", baseline_out=out)
    cases = json.loads(out.read_text())["cases"]
    assert "caseA" in cases  # persisted before the caseB crash -> no data loss


def test_run_mode_resume_skips_already_complete_cases(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("JUDGE_ENABLED", "0")
    monkeypatch.setattr(run_bench, "plan_runs", lambda *, mode: [
        run_bench.RunSpec("caseA", "standard", 1),
        run_bench.RunSpec("caseB", "standard", 1),
    ])
    captured: list[str] = []

    def fake_capture(case_id: str, judge: object) -> tuple[CaseScore | None, list[str]]:
        captured.append(case_id)
        return _score(1.0), ["scored"]

    monkeypatch.setattr(run_bench, "_capture_case_run", fake_capture)
    out = tmp_path / "bl.json"
    run_bench._run_mode("calibrate", baseline_out=out)  # first pass: both captured
    assert captured == ["caseA", "caseB"]
    captured.clear()
    run_bench._run_mode("calibrate", baseline_out=out)  # resume: both complete -> skipped
    assert captured == []


# --- commit_sha provenance (Tier-3 DX: a committed baseline must be reproducible) ----------


def test_resolve_commit_sha_returns_real_short_sha() -> None:
    # The literal "HEAD" recorded a non-reproducible provenance. The writer must pin the
    # actual repo SHA so a committed baseline is traceable to the code that produced it.
    sha = run_bench._resolve_commit_sha()
    assert sha != "HEAD"
    assert re.fullmatch(r"[0-9a-f]{7,40}", sha), f"expected a short git sha, got {sha!r}"


def test_resolve_commit_sha_falls_back_to_head_when_git_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No git / detached / not-a-repo must not crash the capture: degrade to "HEAD".
    def boom(*_a: object, **_k: object) -> object:
        raise subprocess.CalledProcessError(128, "git")

    monkeypatch.setattr(run_bench.subprocess, "run", boom)
    assert run_bench._resolve_commit_sha() == "HEAD"


def test_run_mode_writes_resolved_commit_sha(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # _run_mode must wire the resolved SHA into the written baseline, not the literal "HEAD".
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("JUDGE_ENABLED", "0")
    monkeypatch.setattr(run_bench, "_resolve_commit_sha", lambda: "deadbee")
    monkeypatch.setattr(run_bench, "plan_runs", lambda *, mode: [
        run_bench.RunSpec("caseA", "standard", 1),
    ])
    monkeypatch.setattr(
        run_bench, "_capture_case_run", lambda case_id, judge: (_score(1.0), ["scored"])
    )
    out = tmp_path / "bl.json"
    run_bench._run_mode("calibrate", baseline_out=out)
    assert json.loads(out.read_text())["commit_sha"] == "deadbee"
