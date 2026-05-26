"""Release-gate regression rule (spec §11.7): fail if median F1 drops
>=10pp on >=2 of 5 cases vs the committed baseline."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

DROP_THRESHOLD = 0.10
MIN_REGRESSED_CASES = 2


@dataclass(frozen=True)
class RegressionResult:
    failed: bool
    regressed_cases: list[str]
    deltas: dict[str, float]


def check_regression(
    baseline: dict[str, Any],
    current_f1: dict[str, float],
) -> RegressionResult:
    """Compare current F1 scores against baseline; flag regressions >= 10pp."""
    base_cases: dict[str, Any] = baseline.get("cases", {})
    deltas: dict[str, float] = {}
    regressed: list[str] = []
    for case_id, base in base_cases.items():
        base_f1 = float(base["median_f1"])
        cur_f1 = float(current_f1.get(case_id, 0.0))
        delta = cur_f1 - base_f1
        deltas[case_id] = delta
        if -delta >= DROP_THRESHOLD:
            regressed.append(case_id)
    return RegressionResult(
        failed=len(regressed) >= MIN_REGRESSED_CASES,
        regressed_cases=sorted(regressed),
        deltas=deltas,
    )


def render(result: RegressionResult) -> str:
    head = "REGRESSION FAIL" if result.failed else "OK"
    rows = "\n".join(f"  {c}: {d:+.3f}" for c, d in sorted(result.deltas.items()))
    return f"[{head}] regressed={result.regressed_cases}\n{rows}"


def main(result: RegressionResult) -> None:
    print(render(result))
    if result.failed:
        sys.exit(1)
