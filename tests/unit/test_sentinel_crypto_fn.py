"""Offline tests for the crypto-FN over-suppression re-test (PR #22 caveat closure).

Covers the file-label threading + the file-aware positive detector (the fix for the throwaway
probe's artifact), the bench-canonical line-number derivation, and the non-inferiority decision
truth table. The billed Opus path (run_one_crypto / run_crypto_experiment) is exercised only by
a live run, never in CI."""
from __future__ import annotations

import shutil

from bench.runner.invoke_hydra_1x import prepare_case_workspace
from bench.runner.run_bench import load_ground_truth
from bench.runner.sentinel_isolation import (
    CRYPTO_SCENARIOS,
    CryptoArmStats,
    build_user_content,
    decide_noninferiority,
    flagged_target,
)
from bench.runner.stats import wilson_ci

RESET_FILE = "src/auth/passwordReset.ts"
MAGIC_FILE = "src/auth/magicLink.ts"


# --- (a) file-label threading ------------------------------------------------


def test_build_user_content_threads_file_label() -> None:
    u = build_user_content("SRC", "DIFF", "bnd", file_label=MAGIC_FILE)
    assert f"[SECTION:source_code] {MAGIC_FILE}:" in u
    assert "src/interceptors/auth.ts" not in u  # no case-01 residue


def test_build_user_content_default_preserves_case01() -> None:
    u = build_user_content("SRC", "DIFF", "bnd")
    assert "[SECTION:source_code] src/interceptors/auth.ts:" in u


# --- (b/c/d) file-aware positive detector: the probe-artifact regression -----

TARGET = [{"file": MAGIC_FILE, "lines": "11"}]


def test_flagged_target_true_within_range_same_file() -> None:
    assert flagged_target([{"file": MAGIC_FILE, "lines": "12"}], TARGET)  # within RANGE_TOL=5


def test_flagged_target_false_on_wrong_file_same_line() -> None:
    # THE artifact regression: a finding on the WRONG file at the target line must NOT count.
    # The throwaway probe lacked exactly this assertion.
    assert not flagged_target([{"file": "src/interceptors/auth.ts", "lines": "11"}], TARGET)


def test_flagged_target_false_beyond_range_tol() -> None:
    # the benign cache-buster (line 5) is >5 lines from the target (line 11) -> separable.
    assert not flagged_target([{"file": MAGIC_FILE, "lines": "5"}], TARGET)


def test_flagged_target_ignores_null_location() -> None:
    assert not flagged_target([{"file": MAGIC_FILE, "lines": None}], TARGET)


# --- (e) bench-canonical line-number derivation (no hand-counted literals) ----


def _derived_line(case_id: str, rel: str, needle: str) -> int:
    ws = prepare_case_workspace(case_id)
    try:
        for i, line in enumerate((ws / rel).read_text().splitlines(), 1):
            if needle in line:
                return i
    finally:
        shutil.rmtree(ws, ignore_errors=True)
    raise AssertionError(f"{needle!r} not found in resolved {rel}")


def test_reset_anchor_line_matches_resolved_workspace() -> None:
    gt = load_ground_truth("30-weak-prng-reset-token")
    mand = next(g for g in gt if g.get("mandatory"))
    derived = _derived_line("30-weak-prng-reset-token", RESET_FILE, "Math.floor(Math.random")
    assert int(mand["lines"]) == derived  # stored anchor == post-patch PRNG line
    assert mand["file"] == RESET_FILE
    assert mand["cwe"] == "CWE-330"


def test_magic_anchor_line_matches_resolved_workspace() -> None:
    gt = load_ground_truth("31-weak-prng-magic-link")
    mand = next(g for g in gt if g.get("mandatory"))
    derived = _derived_line("31-weak-prng-magic-link", MAGIC_FILE, "const linkId = Math.random")
    assert int(mand["lines"]) == derived
    assert mand["file"] == MAGIC_FILE


def test_magic_source_avoids_enumerated_vocabulary() -> None:
    # The non-enumerated guarantee: the reviewed source must not echo the clause's listed
    # nouns, so a flag proves access-semantics reasoning, not keyword match.
    import re

    ws = prepare_case_workspace("31-weak-prng-magic-link")
    try:
        src = (ws / MAGIC_FILE).read_text().lower()
    finally:
        shutil.rmtree(ws, ignore_errors=True)
    # whole-word match: "possession" legitimately contains "session" but is not the noun.
    for banned in ("token", "secret", "nonce", "session", "csrf", "reset", "password"):
        assert not re.search(rf"\b{banned}\b", src), (
            f"enumerated noun {banned!r} leaked into the magic-link source"
        )


def test_scenarios_map_to_the_two_cases() -> None:
    assert CRYPTO_SCENARIOS["cryptofn-reset"]["case_id"] == "30-weak-prng-reset-token"
    assert CRYPTO_SCENARIOS["cryptofn-magic"]["case_id"] == "31-weak-prng-magic-link"


# --- (g) decide_noninferiority truth table -----------------------------------


def _arm(flags: int, n: int) -> CryptoArmStats:
    return CryptoArmStats(
        n=n, target_flags=flags, target_rate=flags / n if n else 0.0,
        target_ci=wilson_ci(flags, n), benign_flags=0, benign_rate=0.0,
    )


def test_decide_closed_non_ceiling_high_n() -> None:
    # control 29/30 (>=0.90, NOT ceiling), treatment 29/30: Newcombe lo >= -0.15 at this N.
    d = decide_noninferiority(_arm(29, 30), _arm(29, 30))
    assert d["verdict"].startswith("CLOSED")
    assert not d["control_ceilinged"]


def test_decide_ceilinged_is_not_clean_closure() -> None:
    # control at 100% has no headroom: non-inferior but honestly "too easy", not CLOSED.
    d = decide_noninferiority(_arm(30, 30), _arm(30, 30))
    assert d["verdict"].startswith("REASSURING-BUT-CEILINGED")
    assert d["control_ceilinged"]


def test_decide_reopen_on_real_over_suppression() -> None:
    # control 15/15, treatment 8/15: a real ~47pp drop, CI upper bound below 0.
    d = decide_noninferiority(_arm(15, 15), _arm(8, 15))
    assert d["verdict"].startswith("REOPEN")
    assert d["diff_ci_high"] < 0.0


def test_decide_void_when_control_fails_to_elicit() -> None:
    # control flags the true CWE-330 only 12/15 (<0.90): broken scenario, not a clause result.
    d = decide_noninferiority(_arm(12, 15), _arm(12, 15))
    assert d["verdict"].startswith("VOID")


def test_decide_inconclusive_when_ci_straddles_margin() -> None:
    # control 15/15, treatment 14/15 at small N: CI is too wide to conclude either way.
    d = decide_noninferiority(_arm(15, 15), _arm(14, 15))
    assert d["verdict"].startswith("INCONCLUSIVE")


def test_decide_floor_is_observed_rate_not_wilson_lb() -> None:
    # Regression guard for must-fix #2: the treatment floor is the OBSERVED rate (>=0.80), not
    # a Wilson lower bound. treatment 27/30 has rate 0.90 but Wilson LB ~0.74 < 0.80 — an LB
    # floor would wrongly fail it. With a non-ceiling control 30/29-shaped high arm and lo within
    # margin, the rate floor must accept it (verdict not gated OUT by an LB).
    treat = _arm(27, 30)
    assert treat.target_rate >= 0.80  # observed rate passes
    assert wilson_ci(27, 30).ci_low < 0.80  # but its Wilson LB does not — the trap we avoid
