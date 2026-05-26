"""Bench runner — orchestration, scoring + baseline writer."""
from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import yaml

from bench.runner.models import GroundTruthFinding
from bench.runner.scoring import CaseScore, score_case

ROOT = Path(__file__).resolve().parents[2]
CASES_DIR = ROOT / "bench" / "cases"
BASELINES_DIR = ROOT / "bench" / "baselines"

FAST_BENCH_CASES = ["01-axios-header-injection", "04-react-effect-infinite-loop"]


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
    full = all 5 cases, standard + deep modes, 3 runs each (release gate).
    """
    if mode == "fast":
        return [RunSpec(c, "standard", 1) for c in FAST_BENCH_CASES]
    if mode == "full":
        return [
            RunSpec(c, m, 3)
            for c in discover_cases()
            for m in ("standard", "deep")
        ]
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


def load_manifest(case_id: str) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load((CASES_DIR / case_id / "manifest.yaml").read_text()))


def run_single_case(case_id: str, candidates_path: Path) -> CaseScore:
    gt = load_ground_truth(case_id)
    candidates = [
        json.loads(line)
        for line in candidates_path.read_text().splitlines()
        if line.strip()
    ]
    return score_case(gt, candidates)


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


def _median_f1_by_case(run_records: list[dict[str, Any]]) -> dict[str, float]:
    """Median F1 per case across the captured runs (the comparison surface for the gate)."""
    by_case: dict[str, list[float]] = {}
    for run in run_records:
        for case_id, score in run["scores"].items():
            by_case.setdefault(case_id, []).append(score.f1)
    return {case_id: statistics.median(v) for case_id, v in by_case.items()}


def gate_against_baseline(current_f1: dict[str, float], baseline_path: Path) -> int:
    """Compare current median F1 against a committed baseline; return exit code (1 on
    release regression, else 0). Prints the report.

    ADVISORY when the baseline is a single retried run per case (the current 1.x
    baseline): the spec §11.7 ≥10pp/≥2-of-5 rule's statistical basis assumes
    median-of-N runs and multi-finding ground truth. Against a single-run, one-GT-
    per-case baseline the gate is variance-prone and structurally blind to a
    single-case quality loss (which only soft-warns). Do NOT wire this into a
    *blocking* CI step until the median-of-N baseline + multi-finding cases land
    (deferred, spec §11.9 amendment). It prints an [ADVISORY] banner in that case.
    """
    from bench.runner.report import check_regression, render

    baseline = json.loads(baseline_path.read_text())
    single_run = all(
        len(c.get("runs", [])) <= 1 for c in baseline.get("cases", {}).values()
    )
    if single_run:
        print(
            "[ADVISORY] single-run baseline — gate is variance-prone and blind to "
            "single-case loss; treat as a smoke signal, not a blocking gate (spec §11.7)."
        )
    result = check_regression(baseline, current_f1)
    print(render(result))
    return 1 if result.failed else 0


def _run_mode(
    mode: str, *, baseline_out: Path | None = None, check_baseline: Path | None = None
) -> int:
    """Drive invoke -> extract -> score -> aggregate for fast/full bench modes.

    Then EITHER write a baseline (capture) OR gate against an existing baseline
    (``check_baseline`` -> exit code). The live invoke path calls
    ``invoke_hydra`` and is cost-gated (not unit-tested); the aggregate + gate
    helpers (`_median_f1_by_case`, `gate_against_baseline`) are unit-tested.
    """
    import shutil

    from bench.runner.extract_findings import extract_from_report
    from bench.runner.invoke_hydra_1x import invoke_hydra, prepare_case_workspace
    from bench.runner.judge import resolve_judge

    try:
        from anthropic import Anthropic

        client: object | None = Anthropic()
    except Exception:
        client = None

    judge = resolve_judge(client=client, model="claude-haiku-4-5-20251001")

    specs = plan_runs(mode=mode)
    run_records: list[dict[str, Any]] = []
    for spec in specs:
        scores_this_run: dict[str, CaseScore] = {}
        for _ in range(spec.runs):
            workspace = prepare_case_workspace(spec.case_id)
            try:
                report_path = invoke_hydra(workspace)
                candidates = extract_from_report(report_path.read_text())
                gt = load_ground_truth(spec.case_id)
                scores_this_run[spec.case_id] = score_case(gt, candidates, judge=judge)
            finally:
                shutil.rmtree(workspace, ignore_errors=True)
        run_records.append({"scores": scores_this_run})

    if check_baseline is not None:
        return gate_against_baseline(_median_f1_by_case(run_records), check_baseline)

    ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    out = baseline_out or (BASELINES_DIR / f"run-{mode}-{ts}.json")
    write_baseline(label=mode, commit_sha="HEAD", runs=run_records, output_path=out)
    print(f"baseline -> {out}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    single = sub.add_parser("score", help="score a single case against a candidates file")
    single.add_argument("--case", required=True, help="case id (e.g. 01-axios-header-injection)")
    single.add_argument("--candidates", required=True, type=Path)
    single.add_argument("--json", action="store_true")

    bench = sub.add_parser("bench", help="run fast or full bench")
    bench.add_argument("--mode", choices=["fast", "full"], required=True)
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
