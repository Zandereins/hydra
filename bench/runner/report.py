"""Release-gate regression rule (spec §11.7).

Gates on **median critical-recall** — not F1. With one mandatory ground-truth finding
per case, F1 is pinned (recall∈{0,1}, precision∼1/k) and cannot move on a correct
answer, so it is a dead gate metric (eval-audit finding). critical-recall ("did Hydra
find the mandatory seeded bug") is the signal that actually moves with quality. F1 is
reported as a diagnostic only.

Rule: release-fail if critical-recall drops >=10pp on >=2 of N cases; soft-warn
(yellow, non-failing) on any single case dropping >15pp. See spec §11.9 amendment for
why this is ADVISORY against a single-run baseline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

GATE_METRIC = "median_critical_recall"  # the metric that moves with quality (1 GT/case)
DROP_THRESHOLD = 0.10  # release-fail: >=2 cases must each drop this much
WARN_THRESHOLD = 0.15  # soft-warn: any single case dropping more than this
MIN_REGRESSED_CASES = 2


@dataclass(frozen=True)
class RegressionResult:
    failed: bool
    regressed_cases: list[str]
    deltas: dict[str, float]  # critical-recall deltas (the GATED metric)
    warned_cases: list[str] = field(default_factory=list)
    f1_deltas: dict[str, float] = field(default_factory=dict)  # diagnostic only, never gated


def check_regression(
    baseline: dict[str, Any],
    current_critical_recall: dict[str, float],
    *,
    current_f1: dict[str, float] | None = None,
) -> RegressionResult:
    """Gate on critical-recall: release-fail on >=2 cases >=10pp drop; soft-warn on
    any case dropping >15pp. F1 deltas are computed only for the diagnostic render."""
    base_cases: dict[str, Any] = baseline.get("cases", {})
    deltas: dict[str, float] = {}
    regressed: list[str] = []
    warned: list[str] = []
    for case_id, base in base_cases.items():
        base_cr = float(base[GATE_METRIC])
        cur_cr = float(current_critical_recall.get(case_id, 0.0))
        delta = cur_cr - base_cr
        deltas[case_id] = delta
        if -delta >= DROP_THRESHOLD:
            regressed.append(case_id)
        if -delta > WARN_THRESHOLD:
            warned.append(case_id)
    f1_deltas: dict[str, float] = {}
    if current_f1 is not None:
        for case_id, base in base_cases.items():
            if "median_f1" in base:
                f1_deltas[case_id] = float(current_f1.get(case_id, 0.0)) - float(base["median_f1"])
    return RegressionResult(
        failed=len(regressed) >= MIN_REGRESSED_CASES,
        regressed_cases=sorted(regressed),
        deltas=deltas,
        warned_cases=sorted(warned),
        f1_deltas=f1_deltas,
    )


def render(result: RegressionResult) -> str:
    head = "REGRESSION FAIL" if result.failed else ("WARN" if result.warned_cases else "OK")
    rows = "\n".join(f"  {c}: crit_recall {d:+.3f}" for c, d in sorted(result.deltas.items()))
    warn = f"\nwarn (>15pp): {result.warned_cases}" if result.warned_cases else ""
    diag = ""
    if result.f1_deltas:
        diag = "\nF1 (diagnostic, not gated):\n" + "\n".join(
            f"  {c}: {d:+.3f}" for c, d in sorted(result.f1_deltas.items())
        )
    return f"[{head}] gated=critical_recall regressed={result.regressed_cases}{warn}\n{rows}{diag}"
