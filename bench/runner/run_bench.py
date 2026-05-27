"""Bench runner — orchestration, scoring + baseline writer."""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import yaml

from bench.runner.models import GroundTruthFinding, NegativeAnchor
from bench.runner.scoring import CaseScore, score_case
from bench.runner.stats import MetricCI, bootstrap_ci, ci_regression, success_rate, wilson_ci

ROOT = Path(__file__).resolve().parents[2]
CASES_DIR = ROOT / "bench" / "cases"
BASELINES_DIR = ROOT / "bench" / "baselines"

FAST_BENCH_CASES = ["01-axios-header-injection", "04-react-effect-infinite-loop"]

# N scored runs per case for the statistical (CI) baseline — spec §4 N≈5. Each "run" is a
# retry-cluster (_capture_case_run retries transient headless failures internally); failed
# clusters are still recorded in outcomes so success-rate stays honest (capture-all).
RUNS_PER_CASE = int(os.environ.get("HYDRA_RUNS_PER_CASE", "5"))


@dataclass(frozen=True)
class RunSpec:
    case_id: str
    hydra_mode: str  # "standard" | "deep"
    runs: int


def discover_cases() -> list[str]:
    """Return sorted case-directory names from CASES_DIR."""
    return sorted(p.name for p in CASES_DIR.iterdir() if p.is_dir())


def plan_runs(*, mode: str) -> list[RunSpec]:
    """Return the list of RunSpec items for the given bench mode.

    fast = cases #1+#4, standard mode, 1 run each (per-commit gate).
    full = all cases, standard + deep modes, 3 runs each (release gate).
    calibrate = all cases, standard mode, RUNS_PER_CASE scored slots each — the P6
      statistical-baseline capture (median + bootstrap CI over N≈5 scored runs).
    """
    if mode == "fast":
        return [RunSpec(c, "standard", 1) for c in FAST_BENCH_CASES]
    if mode == "full":
        return [
            RunSpec(c, m, 3)
            for c in discover_cases()
            for m in ("standard", "deep")
        ]
    if mode == "calibrate":
        return [RunSpec(c, "standard", RUNS_PER_CASE) for c in discover_cases()]
    raise ValueError(f"unknown bench mode: {mode!r}")


def load_ground_truth(case_id: str) -> list[dict[str, Any]]:
    """Load + validate ground truth via GroundTruthFinding (enforces must_mention,
    extra='forbid') so a malformed case fails loudly at load, not silently at scoring."""
    path = CASES_DIR / case_id / "expected_findings.jsonl"
    return [
        GroundTruthFinding.model_validate_json(line).model_dump(mode="json")
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def load_negative_anchors(case_id: str) -> list[dict[str, Any]]:
    """Load + validate benign negative anchors for a case; [] if it ships none.

    Validated via NegativeAnchor (extra='forbid') so a malformed anchor fails loudly at
    load. A candidate overlapping one is scored as an explicit false positive (Track-3 P2)."""
    path = CASES_DIR / case_id / "negative_anchors.jsonl"
    if not path.exists():
        return []
    return [
        NegativeAnchor.model_validate_json(line).model_dump(mode="json")
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def load_manifest(case_id: str) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load((CASES_DIR / case_id / "manifest.yaml").read_text()))


def run_single_case(case_id: str, candidates_path: Path) -> CaseScore:
    """Score a pre-extracted candidates file offline. DETERMINISTIC-only: no LLM judge
    (keyword matching only) — use `bench` mode for judge-backed scoring of live runs."""
    gt = load_ground_truth(case_id)
    candidates = [
        json.loads(line)
        for line in candidates_path.read_text().splitlines()
        if line.strip()
    ]
    return score_case(gt, candidates, negative_anchors=load_negative_anchors(case_id))


def write_baseline(
    label: str,
    commit_sha: str,
    runs: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """Write baseline file with median-of-runs metrics."""
    by_case: dict[str, list[CaseScore]] = {}
    for run in runs:
        for case_id, score in run["scores"].items():
            by_case.setdefault(case_id, []).append(score)

    aggregated = {
        case_id: {
            "median_f1": statistics.median(s.f1 for s in scores),
            "median_recall": statistics.median(s.recall for s in scores),
            "median_precision": statistics.median(s.precision for s in scores),
            "median_critical_recall": statistics.median(s.critical_recall for s in scores),
            "runs": [asdict(s) for s in scores],
        }
        for case_id, scores in by_case.items()
    }

    payload = {
        "label": label,
        "captured_at": datetime.now(UTC).isoformat(),
        "commit_sha": commit_sha,
        "cases": aggregated,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2))


# --- Track-3 P3: statistical (CI) baseline + blocking gate (spec §4) ----------

CI_METRICS = ("critical_recall", "recall", "f1", "false_positive_rate")


def aggregate_outcomes(outcomes: list[str]) -> tuple[int, int, dict[str, int]]:
    """Capture-all reliability summary from per-attempt outcome labels (spec §4):
    (n_attempts, n_scored, failure_modes). Discards nothing — every attempt counts."""
    n_attempts = len(outcomes)
    n_scored = sum(1 for o in outcomes if o == "scored")
    failure_modes: dict[str, int] = {}
    for o in outcomes:
        if o != "scored":
            failure_modes[o] = failure_modes.get(o, 0) + 1
    return n_attempts, n_scored, failure_modes


def metric_cis(scores: list[CaseScore], *, seed: int = 0) -> dict[str, MetricCI]:
    """95% CI per gate metric over one case's scored runs.

    ``critical_recall`` is binary per run (one mandatory finding/case -> caught or not),
    so it uses the Wilson *proportion* interval; bootstrap-of-median is blind on binary
    data (roadmap 0.1). The continuous diagnostic metrics (recall/f1/false_positive_rate)
    keep the bootstrap-of-median CI."""
    cis = {
        m: bootstrap_ci([getattr(s, m) for s in scores], seed=seed)
        for m in CI_METRICS
        if m != "critical_recall"
    }
    crit_caught = sum(1 for s in scores if s.critical_recall >= 1.0)
    cis["critical_recall"] = wilson_ci(crit_caught, len(scores))
    return cis


def write_ci_baseline(
    label: str,
    commit_sha: str,
    per_case: dict[str, dict[str, Any]],
    output_path: Path,
    *,
    confidence: float = 0.95,
    n_resamples: int = 2000,
) -> None:
    """Write a statistical baseline: per case, median + bootstrap CI per metric over N
    scored runs, plus first-class harness success-rate + failure-mode breakdown.

    ``per_case[case]`` carries ``{"scores": list[CaseScore], "outcomes": list[str]}``
    (outcomes = every attempt incl. failures, so success-rate is honest)."""
    cases: dict[str, Any] = {}
    for case_id, data in per_case.items():
        scores: list[CaseScore] = data["scores"]
        outcomes: list[str] = data["outcomes"]
        n_attempts, n_scored, failure_modes = aggregate_outcomes(outcomes)
        cases[case_id] = {
            "n_attempts": n_attempts,
            "n_scored": n_scored,
            "success_rate": success_rate(n_scored=n_scored, n_attempts=n_attempts),
            "failure_modes": failure_modes,
            "metrics": {m: asdict(ci) for m, ci in metric_cis(scores).items()},
        }
    payload = {
        "label": label,
        "captured_at": datetime.now(UTC).isoformat(),
        "commit_sha": commit_sha,
        "statistical": True,
        "confidence": confidence,
        "n_resamples": n_resamples,
        "cases": cases,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2))


def gate_against_ci_baseline(
    current_critical_recall_ci: dict[str, MetricCI], baseline_path: Path
) -> int:
    """Blocking CI gate (spec §4): fail (exit 1) when the challenger's critical-recall
    CI is disjoint-and-below the baseline's on >=2 cases. Zero scored runs -> exit 2
    (harness outage, not a regression). Overlapping CIs -> exit 0."""
    if not current_critical_recall_ci:
        print("[ERROR] no scored runs — harness failure, not a quality regression")
        return 2
    baseline = json.loads(baseline_path.read_text())
    base_ci: dict[str, MetricCI] = {}
    for case_id, c in baseline.get("cases", {}).items():
        cr = c.get("metrics", {}).get("critical_recall")
        if cr is not None:
            base_ci[case_id] = MetricCI(
                median=float(cr["median"]), ci_low=float(cr["ci_low"]), ci_high=float(cr["ci_high"])
            )
    result = ci_regression(base_ci, current_critical_recall_ci)
    head = "CI-REGRESSION FAIL" if result.failed else "OK"
    print(
        f"[{head}] gated=critical_recall (non-overlapping CIs) "
        f"regressed={result.regressed_cases}"
    )
    for case_id, detail in sorted(result.details.items()):
        print(f"  {case_id}: {detail}")
    return 1 if result.failed else 0


MAX_ATTEMPTS = 5  # retry transient headless failures (timeout / no-report / action-less)


def _median_metric_by_case(run_records: list[dict[str, Any]], attr: str) -> dict[str, float]:
    """Median of CaseScore.<attr> per case across the captured runs."""
    by_case: dict[str, list[float]] = {}
    for run in run_records:
        for case_id, score in run["scores"].items():
            by_case.setdefault(case_id, []).append(getattr(score, attr))
    return {case_id: statistics.median(v) for case_id, v in by_case.items()}


def _capture_case_run(case_id: str, judge: object) -> tuple[CaseScore | None, list[str]]:
    """One median-slot for a case: retry transient headless failures up to MAX_ATTEMPTS,
    accepting the first scored run with recall>0 (else the last scored run, else None).
    Records a per-attempt outcome label for telemetry. Genuine errors (git apply,
    CalledProcessError, Python/SDK exceptions) propagate — only timeout/no-report/
    action-less are retried."""
    import shutil

    from bench.runner.extract_findings import extract_candidates
    from bench.runner.invoke_hydra_1x import invoke_hydra, prepare_case_workspace

    outcomes: list[str] = []
    last_scored: CaseScore | None = None
    for _ in range(MAX_ATTEMPTS):
        workspace = prepare_case_workspace(case_id)
        try:
            report_path = invoke_hydra(workspace)
            candidates = extract_candidates(report_path)  # prefer .findings.json sidecar
            score = score_case(
                load_ground_truth(case_id),
                candidates,
                judge=judge,  # type: ignore[arg-type]
                negative_anchors=load_negative_anchors(case_id),
            )
        except subprocess.TimeoutExpired:
            outcomes.append("timeout")
            continue
        except RuntimeError:  # invoke_hydra: "no report produced"
            outcomes.append("no_report")
            continue
        finally:
            shutil.rmtree(workspace, ignore_errors=True)
        last_scored = score
        if score.recall > 0:
            outcomes.append("scored")
            return score, outcomes
        outcomes.append("action_less")
    return last_scored, outcomes


def _print_telemetry(
    telemetry: list[dict[str, Any]], per_case: dict[str, dict[str, Any]] | None = None
) -> None:
    """Surface harness reliability (don't silently discard failed attempts) — per-case
    success-rate + failure-mode breakdown (spec §4: success-rate is first-class)."""
    total_attempts = sum(t["attempts"] for t in telemetry)
    scored = sum(1 for t in telemetry if t["accepted"])
    print(f"[telemetry] slots={len(telemetry)} scored={scored} total_attempts={total_attempts}")
    if per_case:
        for case_id, d in sorted(per_case.items()):
            n_att, n_sc, fails = aggregate_outcomes(d["outcomes"])
            rate = success_rate(n_scored=n_sc, n_attempts=n_att)
            print(f"  {case_id}: success_rate={rate:.2f} ({n_sc}/{n_att}) failures={fails}")
    else:
        for t in telemetry:
            print(f"  {t['case']}: accepted={t['accepted']} attempts={t['outcomes']}")


def gate_against_baseline(
    current_critical_recall: dict[str, float],
    baseline_path: Path,
    *,
    current_f1: dict[str, float] | None = None,
) -> int:
    """Compare current critical-recall against a committed baseline; return exit code.

    Gates on critical-recall (the metric that moves with quality), not the pinned F1.
    ADVISORY when the baseline is a single retried run per case: returns 0 regardless
    of the result (prints the report + an [ADVISORY] banner) so a single-run baseline
    can NEVER hard-fail CI — the §11.7 ≥10pp/≥2-of-5 rule's basis assumes median-of-N
    + multi-finding GT (deferred, spec §11.9 amendment).
    """
    from bench.runner.report import check_regression, render

    if not current_critical_recall:
        # zero scored runs = total harness outage, NOT a quality regression — exit 2 so
        # CI can distinguish infrastructure failure from a real regression (exit 1).
        print("[ERROR] no scored runs — harness failure, not a quality regression")
        return 2

    baseline = json.loads(baseline_path.read_text())
    single_run = all(len(c.get("runs", [])) <= 1 for c in baseline.get("cases", {}).values())
    result = check_regression(baseline, current_critical_recall, current_f1=current_f1)
    if single_run:
        print(
            "[ADVISORY] single-run baseline — gate is advisory only and will NOT fail CI; "
            "treat as a smoke signal until a median-of-N baseline lands (spec §11.7/§11.9)."
        )
        print(render(result))
        return 0
    print(render(result))
    return 1 if result.failed else 0


def _run_mode(
    mode: str, *, baseline_out: Path | None = None, check_baseline: Path | None = None
) -> int:
    """Drive invoke -> extract -> score -> aggregate (with retry) for fast/full bench.

    Then EITHER write a baseline (capture) OR gate against an existing baseline
    (``check_baseline`` -> exit code). The live invoke path is cost-gated (not
    unit-tested); the retry/aggregate/gate helpers are unit-tested.
    """
    judge_model = os.environ.get("HYDRA_JUDGE_MODEL", "claude-haiku-4-5-20251001")
    try:
        from anthropic import Anthropic

        client: object | None = Anthropic()
    except ImportError:  # judge extra not installed -> deterministic keyword-only run
        client = None

    from bench.runner.judge import resolve_judge

    judge = resolve_judge(client=client, model=judge_model)

    run_records: list[dict[str, Any]] = []  # legacy point-baseline (advisory gate compat)
    per_case: dict[str, dict[str, Any]] = {}  # capture-all: scored runs + every outcome
    telemetry: list[dict[str, Any]] = []
    for spec in plan_runs(mode=mode):
        for _ in range(spec.runs):
            score, outcomes = _capture_case_run(spec.case_id, judge)
            slot = per_case.setdefault(spec.case_id, {"scores": [], "outcomes": []})
            slot["outcomes"].extend(outcomes)
            telemetry.append(
                {"case": spec.case_id, "attempts": len(outcomes), "outcomes": outcomes,
                 "accepted": score is not None}
            )
            if score is not None:
                slot["scores"].append(score)
                run_records.append({"scores": {spec.case_id: score}})
    _print_telemetry(telemetry, per_case)

    if check_baseline is not None:
        baseline = json.loads(check_baseline.read_text())
        if baseline.get("statistical"):  # CI baseline -> blocking CI gate (spec §4)
            current_cr = {
                cid: metric_cis(d["scores"])["critical_recall"]
                for cid, d in per_case.items() if d["scores"]
            }
            return gate_against_ci_baseline(current_cr, check_baseline)
        return gate_against_baseline(  # legacy single-run baseline -> advisory gate
            _median_metric_by_case(run_records, "critical_recall"),
            check_baseline,
            current_f1=_median_metric_by_case(run_records, "f1"),
        )

    ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    out = baseline_out or (BASELINES_DIR / f"run-{mode}-{ts}.json")
    write_ci_baseline(label=mode, commit_sha="HEAD", per_case=per_case, output_path=out)
    print(f"statistical baseline -> {out}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    single = sub.add_parser("score", help="score a single case against a candidates file")
    single.add_argument("--case", required=True, help="case id (e.g. 01-axios-header-injection)")
    single.add_argument("--candidates", required=True, type=Path)
    single.add_argument("--json", action="store_true")

    bench = sub.add_parser("bench", help="run fast or full bench")
    bench.add_argument("--mode", choices=["fast", "full", "calibrate"], required=True)
    bench.add_argument("--baseline-out", type=Path, default=None)
    bench.add_argument(
        "--check-baseline",
        type=Path,
        default=None,
        help="compare results against this baseline and exit 1 on release regression",
    )

    args = parser.parse_args()

    if args.command == "bench":
        raise SystemExit(
            _run_mode(args.mode, baseline_out=args.baseline_out, check_baseline=args.check_baseline)
        )

    score = run_single_case(args.case, args.candidates)
    if args.json:
        print(json.dumps(score.__dict__, indent=2))
    else:
        print(
            f"Case {args.case}: F1={score.f1:.2f} R={score.recall:.2f} "
            f"P={score.precision:.2f} crit_R={score.critical_recall:.2f}"
        )


if __name__ == "__main__":
    main()
