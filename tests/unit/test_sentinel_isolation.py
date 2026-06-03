"""Offline tests for the Sentinel isolation harness: prompt assembly, epilog parsing,
flag/guardrail detection, the Fisher exact, and the keep/reject/inconclusive decision.
The billed Opus path is exercised only by a live smoke run, never in CI."""
from __future__ import annotations

import pytest

from bench.runner.sentinel_isolation import (
    SELECTIVITY_BULLET,
    ArmStats,
    RunResult,
    build_sentinel_system,
    build_user_content,
    caught_mandatory,
    decide,
    fisher_one_sided_less,
    flagged_anchor,
    parse_findings,
    summarize,
)
from bench.runner.stats import wilson_ci

ANCHOR = [{"file": "src/interceptors/auth.ts", "lines": "12-15"}]
MANDATORY_LINES = "23-27"
BND = "abc123abc123"  # 12-hex-shaped boundary


def _advisors_md() -> str:
    from bench.runner.sentinel_isolation import ADVISORS_MD

    return ADVISORS_MD.read_text()


# --- prompt assembly: arms differ by EXACTLY the one bullet, nothing leaks ---


def _no_uppercase_placeholder(s: str) -> bool:
    import re

    return not re.search(r"\{\{[A-Z_]+\}\}", s)  # literal {{file}} examples are allowed


def test_control_prompt_has_no_selectivity_and_no_placeholders() -> None:
    sys = build_sentinel_system(_advisors_md(), boundary=BND, with_edit=False)
    assert _no_uppercase_placeholder(sys)
    assert "SELECTIVITY" not in sys
    assert BND in sys  # boundary resolved into the prompt
    assert "You are Sentinel" in sys


def test_edit_prompt_inserts_exactly_the_selectivity_bullet() -> None:
    control = build_sentinel_system(_advisors_md(), boundary=BND, with_edit=False)
    treat = build_sentinel_system(_advisors_md(), boundary=BND, with_edit=True)
    assert _no_uppercase_placeholder(treat)
    assert SELECTIVITY_BULLET in treat
    # The ONLY difference between arms is the inserted bullet (+ its newline).
    assert treat.replace(SELECTIVITY_BULLET + "\n", "", 1) == control


def test_edit_bullet_lands_after_dependency_risk() -> None:
    treat = build_sentinel_system(_advisors_md(), boundary=BND, with_edit=True)
    assert treat.index("Dependency risk") < treat.index("SELECTIVITY")
    assert treat.index("SELECTIVITY") < treat.index("For SERIOUS or CATASTROPHIC")


def test_user_content_frozen_shape() -> None:
    u = build_user_content("SRC_BODY_X", "DIFF_BODY_Y", BND)
    assert f"USER CODE [{BND}]" in u
    assert "SRC_BODY_X" in u  # post-patch source embedded
    assert "DIFF_BODY_Y" in u
    assert "[SECTION:diff_context]" in u


# --- epilog parsing: boundary-keyed, degraded on absence ---


def _epilog(boundary: str, findings_json: str) -> str:
    return (
        "prose...\nPOSITION: CONCERN\n"
        f"---HYDRA-STRUCTURED [{boundary}]---\n"
        f'{{"advisor":"sentinel","position":"CONCERN","findings":{findings_json}}}\n'
        f"---END-HYDRA-STRUCTURED [{boundary}]---"
    )


def test_parse_findings_extracts_array() -> None:
    raw = _epilog(BND, '[{"id":"Se-1","file":"a.ts","lines":"1-2","severity":"SERIOUS"}]')
    out = parse_findings(raw, BND)
    assert len(out) == 1 and out[0]["id"] == "Se-1"


def test_parse_findings_empty_array_ok() -> None:
    assert parse_findings(_epilog(BND, "[]"), BND) == []


def test_parse_findings_missing_epilog_raises() -> None:
    with pytest.raises(ValueError):
        parse_findings("prose only, no epilog", BND)


def test_parse_findings_wrong_boundary_raises() -> None:
    # an epilog keyed to a different boundary must not be accepted (injection defense)
    with pytest.raises(ValueError):
        parse_findings(_epilog("deadbeefdead", "[]"), BND)


# --- flag + guardrail detection (location-only, RANGE_TOL=5) ---


def test_flagged_anchor_true_on_overlap() -> None:
    assert flagged_anchor([{"file": "src/interceptors/auth.ts", "lines": "13-14"}], ANCHOR)


def test_flagged_anchor_false_on_mandatory_location() -> None:
    # a finding at 23-27 is 8 lines from the anchor (>tol 5): never mis-scored as the FP
    assert not flagged_anchor([{"file": "src/interceptors/auth.ts", "lines": "23-27"}], ANCHOR)


def test_flagged_anchor_ignores_null_lines() -> None:
    assert not flagged_anchor([{"file": "src/interceptors/auth.ts", "lines": None}], ANCHOR)


def test_caught_mandatory_true_at_auth_location() -> None:
    assert caught_mandatory(
        [{"file": "src/interceptors/auth.ts", "lines": "23-27"}], MANDATORY_LINES
    )


def test_caught_mandatory_false_at_anchor_location() -> None:
    assert not caught_mandatory(
        [{"file": "src/interceptors/auth.ts", "lines": "12-15"}], MANDATORY_LINES
    )


# --- Fisher exact one-sided (B < A) ---


def test_fisher_significant_total_suppression() -> None:
    # 4/10 control -> 0/10 treatment: the smallest decisive case, p ~ 0.043
    p = fisher_one_sided_less(4, 10, 0, 10)
    assert 0.03 < p < 0.05


def test_fisher_not_significant_small_effect() -> None:
    assert fisher_one_sided_less(4, 10, 2, 10) > 0.10


def test_fisher_no_flags_either_arm_is_one() -> None:
    assert fisher_one_sided_less(0, 10, 0, 10) == pytest.approx(1.0)


# --- decision rule: KEEP / REJECT / INCONCLUSIVE ---


def _arm(flags: int, n: int, catches: int) -> ArmStats:
    return ArmStats(
        n=n, flags=flags, flag_rate=flags / n, flag_ci=wilson_ci(flags, n),
        mandatory_catches=catches, mandatory_rate=catches / n, mandatory_ci=wilson_ci(catches, n),
    )


def test_decide_keep_on_significant_disjoint_with_guardrail() -> None:
    d = decide(_arm(8, 10, 10), _arm(0, 10, 10))
    assert d["verdict"].startswith("KEEP")
    assert d["guardrail_ok"] and d["fp_wilson_disjoint_below"]


def test_decide_reject_when_guardrail_fails() -> None:
    # same FP win, but treatment drops the mandatory finding -> REJECT regardless
    d = decide(_arm(8, 10, 10), _arm(0, 10, 4))
    assert d["verdict"].startswith("REJECT")


def test_decide_inconclusive_on_small_effect() -> None:
    d = decide(_arm(4, 10, 10), _arm(2, 10, 10))
    assert d["verdict"].startswith("INCONCLUSIVE")


# --- summarize excludes degraded runs from denominators ---


def test_summarize_excludes_degraded() -> None:
    runs = [
        RunResult("A", 0, "n", 1, True, True, degraded=False, raw_len=10),
        RunResult("A", 1, "n", 0, False, True, degraded=False, raw_len=10),
        RunResult("A", 2, "n", 0, False, False, degraded=True, raw_len=0),  # excluded
    ]
    s = summarize("A", runs)
    assert s.n == 2  # the degraded run is not counted
    assert s.flags == 1
    assert s.mandatory_catches == 2
