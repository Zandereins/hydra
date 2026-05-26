"""CI baseline writer + blocking CI gate wiring (Track-3 P3b, spec §4)."""
from __future__ import annotations

import json
from pathlib import Path

from bench.runner.run_bench import (
    aggregate_outcomes,
    gate_against_ci_baseline,
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
    assert cis["critical_recall"] == MetricCI(1.0, 1.0, 1.0)


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
