"""Drive 1.x Hydra against each bench case to capture baseline candidates.

Runs 1.x in a scratch worktree — NEVER against the current tree (P-3).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess  # noqa: S404 — TODO(§18.4): route through run_tool once PATH handling is extended
import tempfile
from pathlib import Path
from typing import Any

from bench.runner.extract_findings import extract_from_report
from bench.runner.run_bench import CASES_DIR, run_single_case, write_baseline

HYDRA_1X_REF = os.environ.get("HYDRA_1X_REF", "3506f93")
REPO_ROOT = Path(__file__).resolve().parents[2]


def checkout_scratch(sha: str) -> Path:
    scratch = Path(tempfile.mkdtemp(prefix=f"hydra-1x-{sha}-"))
    subprocess.run(
        ["git", "-C", str(REPO_ROOT), "worktree", "add", "--detach", str(scratch), sha],
        check=True,
    )
    return scratch


def apply_diff(worktree: Path, diff_path: Path) -> None:
    subprocess.run(
        ["git", "-C", str(worktree), "apply", "--3way", str(diff_path)],
        check=False,
    )


def invoke_hydra(worktree: Path) -> Path:
    """Run Claude Code headless against the worktree, invoke `/hydra this`."""
    subprocess.run(
        ["claude", "--print", "--cwd", str(worktree), "/hydra this"],
        check=True,
        capture_output=True,
        text=True,
        timeout=600,
    )
    reports = sorted((worktree / ".hydra" / "reports").glob("hydra-*.md"))
    if not reports:
        raise RuntimeError(f"no report produced in {worktree}/.hydra/reports")
    return reports[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", nargs="*", default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "bench" / "baselines" / "hydra-1.x-2026-04-17.json",
    )
    args = parser.parse_args()

    case_ids = args.cases or [p.name for p in sorted(CASES_DIR.iterdir()) if p.is_dir()]

    scratch = checkout_scratch(HYDRA_1X_REF)
    try:
        scores_by_case: dict[str, Any] = {}
        for case_id in case_ids:
            diff_path = CASES_DIR / case_id / "diff.patch"
            apply_diff(scratch, diff_path)
            report_path = invoke_hydra(scratch)
            candidates = extract_from_report(report_path.read_text())
            candidates_out = REPO_ROOT / "bench" / "runs" / "1x" / f"{case_id}.jsonl"
            candidates_out.parent.mkdir(parents=True, exist_ok=True)
            candidates_out.write_text("\n".join(json.dumps(c) for c in candidates))
            score = run_single_case(case_id, candidates_out)
            scores_by_case[case_id] = score
            subprocess.run(["git", "-C", str(scratch), "reset", "--hard", "HEAD"], check=True)

        write_baseline(
            label=f"hydra-1.x@{HYDRA_1X_REF}",
            commit_sha=HYDRA_1X_REF,
            runs=[{"scores": scores_by_case}],
            output_path=args.output,
        )
        print(f"baseline → {args.output}")
    finally:
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "worktree", "remove", "--force", str(scratch)],
            check=False,
        )


if __name__ == "__main__":
    main()
