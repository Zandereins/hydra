"""`python -m hydra <command>` entrypoint. Currently: `ground`."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hydra.envelopes import AdvisorFinding, GroundingStatus
from hydra.grounding import ground_finding, summarize


def _cmd_ground(args: argparse.Namespace) -> int:
    repo = Path(args.repo)
    findings = [
        AdvisorFinding.model_validate_json(line)
        for line in Path(args.findings).read_text().splitlines()
        if line.strip()
    ]
    for finding in findings:
        ground_finding(finding, repo)

    summary = summarize(findings)
    print(summary.render())

    if args.out:
        Path(args.out).write_text(
            "\n".join(f.model_dump_json() for f in findings)
        )

    if args.strict and any(f.grounding == GroundingStatus.PATH_ESCAPE for f in findings):
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hydra")
    sub = parser.add_subparsers(dest="command", required=True)

    ground = sub.add_parser("ground", help="deterministic citation/grounding check")
    ground.add_argument("--findings", required=True, help="JSONL of AdvisorFinding")
    ground.add_argument("--repo", required=True, help="repo root for citation resolution")
    ground.add_argument("--out", help="write grounded findings JSONL here")
    ground.add_argument("--strict", action="store_true", help="exit 1 if any PATH_ESCAPE")
    ground.set_defaults(func=_cmd_ground)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
