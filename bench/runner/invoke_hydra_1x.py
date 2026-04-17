"""Drive 1.x Hydra against each bench case workspace to capture baseline candidates."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess  # noqa: S404 — TODO(§18.4): route through run_tool once PATH handling is extended
import tempfile
from pathlib import Path
from typing import Any

from bench.runner.extract_findings import extract_from_report
from bench.runner.run_bench import CASES_DIR, load_ground_truth, write_baseline
from bench.runner.scoring import score_case

REPO_ROOT = Path(__file__).resolve().parents[2]
HYDRA_1X_LABEL = "hydra-1.x@3506f93"
COMMIT_SHA = "3506f93"
HYDRA_TIMEOUT_S = int(os.environ.get("HYDRA_TIMEOUT_S", "600"))


def prepare_case_workspace(case_id: str) -> Path:
    """Copy case workspace to tmpdir, git-init, commit base, apply diff.

    Returns path to the initialized scratch dir with the case diff applied
    in the working tree (uncommitted) — so Hydra 1.x sees the PR diff.
    """
    case_dir = CASES_DIR / case_id
    workspace_src = case_dir / "workspace"
    if not workspace_src.is_dir():
        raise RuntimeError(f"no workspace/ dir for case {case_id}")

    scratch = Path(tempfile.mkdtemp(prefix=f"hydra-case-{case_id}-"))
    shutil.copytree(workspace_src, scratch, dirs_exist_ok=True)

    for argv in (
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        ["git", "-c", "user.email=bench@hydra.local", "-c", "user.name=bench",
         "commit", "-qm", "base"],
    ):
        subprocess.run(argv, cwd=scratch, check=True)

    diff_path = case_dir / "diff.patch"
    try:
        subprocess.run(
            ["git", "apply", "--whitespace=fix", str(diff_path)],
            cwd=scratch, check=True,
        )
    except subprocess.CalledProcessError as e:
        shutil.rmtree(scratch, ignore_errors=True)
        raise RuntimeError(
            f"git apply failed for {diff_path} in workspace {scratch}"
        ) from e

    return scratch


def invoke_hydra(workspace: Path) -> Path:
    """Run Claude Code headless with /hydra this in the workspace dir."""
    subprocess.run(
        ["claude", "--print", "/hydra this"],
        cwd=str(workspace),
        check=True,
        capture_output=True,
        text=True,
        timeout=HYDRA_TIMEOUT_S,
    )
    reports = sorted((workspace / ".hydra" / "reports").glob("hydra-*.md"))
    if not reports:
        raise RuntimeError(f"no report produced in {workspace}/.hydra/reports")
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

    scores_by_case: dict[str, Any] = {}
    for case_id in case_ids:
        workspace = prepare_case_workspace(case_id)
        try:
            report_path = invoke_hydra(workspace)
            candidates = extract_from_report(report_path.read_text())
            candidates_out = REPO_ROOT / "bench" / "runs" / "1x" / f"{case_id}.jsonl"
            candidates_out.parent.mkdir(parents=True, exist_ok=True)
            candidates_out.write_text("\n".join(json.dumps(c) for c in candidates))
            scores_by_case[case_id] = score_case(load_ground_truth(case_id), candidates)
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    write_baseline(
        label=HYDRA_1X_LABEL,
        commit_sha=COMMIT_SHA,
        runs=[{"scores": scores_by_case}],
        output_path=args.output,
    )
    print(f"baseline → {args.output}")


if __name__ == "__main__":
    main()
