"""Release-gate regression rule (spec §11.7): fail the release if median F1 drops
>=10pp on >=2 of 5 cases vs the committed baseline; soft-warn (yellow, non-failing)
on any single case dropping >15pp."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any

DROP_THRESHOLD = 0.10  # release-fail: >=2 cases must each drop this much
WARN_THRESHOLD = 0.15  # soft-warn: any single case dropping more than this (fast-bench yellow)
MIN_REGRESSED_CASES = 2


@dataclass(frozen=True)
class RegressionResult:
    failed: bool
    regressed_cases: list[str]
    deltas: dict[str, float]
    warned_cases: list[str] = field(default_factory=list)


def check_regression(
    baseline: dict[str, Any],
    current_f1: dict[str, float],
) -> RegressionResult:
    """Compare current F1 against baseline: release-fail on >=2 cases >=10pp drop;
    soft-warn (non-failing) on any case dropping >15pp (spec §11.7)."""
    base_cases: dict[str, Any] = baseline.get("cases", {})
    deltas: dict[str, float] = {}
    regressed: list[str] = []
    warned: list[str] = []
    for case_id, base in base_cases.items():
        base_f1 = float(base["median_f1"])
        cur_f1 = float(current_f1.get(case_id, 0.0))
        delta = cur_f1 - base_f1
        deltas[case_id] = delta
        if -delta >= DROP_THRESHOLD:
            regressed.append(case_id)
        if -delta > WARN_THRESHOLD:
            warned.append(case_id)
    return RegressionResult(
        failed=len(regressed) >= MIN_REGRESSED_CASES,
        regressed_cases=sorted(regressed),
        deltas=deltas,
        warned_cases=sorted(warned),
    )


def render(result: RegressionResult) -> str:
    head = "REGRESSION FAIL" if result.failed else ("WARN" if result.warned_cases else "OK")
    rows = "\n".join(f"  {c}: {d:+.3f}" for c, d in sorted(result.deltas.items()))
    warn = f"\nwarn (>15pp): {result.warned_cases}" if result.warned_cases else ""
    return f"[{head}] regressed={result.regressed_cases}{warn}\n{rows}"


def main(result: RegressionResult) -> None:
    print(render(result))
    if result.failed:
        sys.exit(1)
