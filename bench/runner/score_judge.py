"""`score-judge` CLI seam: run the REAL judge over the gold-set, report accuracy +
leniency/strictness bias, and (with --check) gate JUDGE-prompt edits via exit code.

Live + BILLED (a sibling of `bench`, NOT the offline keyword-only `score`): one judge call
per gold pair. This is the *cheap* metric for routing JUDGE-prompt edits — re-run it
before/after a judge change and keep the edit only if accuracy holds — versus the expensive
full `bench --mode calibrate` that an advisor/prompt edit requires.

Exit convention 0=pass / 1=regression / 2=harness-outage, mirroring run_bench's
gate_against_*_baseline. An OUTAGE (missing credential / no SDK / unreadable-or-empty
gold-set / billing declined / a fully-degraded auth-rejected run) is deliberately kept
distinct from a real accuracy regression so a routing loop never reads infra failure as a
bad edit. The only API-billed path (Anthropic() + make_judge) lives in run_score_judge;
the gate/format helpers are pure and unit-tested offline (see tests/unit/test_score_judge.py).
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict

from bench.runner.judge_eval import JudgeMetrics, evaluate_judge, load_gold_set

DEFAULT_JUDGE_MODEL = "claude-haiku-4-5-20251001"


def resolve_model(cli_model: str | None) -> str:
    """--model > $HYDRA_JUDGE_MODEL > the haiku default."""
    return cli_model or os.environ.get("HYDRA_JUDGE_MODEL", DEFAULT_JUDGE_MODEL)


def has_anthropic_credential() -> bool:
    """True if the SDK can authenticate from the env. Anthropic() reads BOTH
    ANTHROPIC_API_KEY and ANTHROPIC_AUTH_TOKEN, so accept either — checking only the former
    would reject a valid AUTH_TOKEN-only setup as a false outage."""
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def is_total_judge_outage(m: JudgeMetrics) -> bool:
    """True when the judge emitted ZERO MATCH verdicts across a non-empty set
    (true_match + false_match == 0). That is almost certainly a degraded/auth-rejected run —
    an invalid key 401s every call and make_judge collapses each to NO_MATCH, yielding a
    plausible-looking ~0.50 accuracy on the balanced gold-set — not a real judge that
    genuinely matches none of the expected-MATCH pairs. Routed to exit 2 so it is never read
    as a clean regression. RESIDUAL LIMITATION: a PARTIAL degradation (some calls succeed,
    some 401) is NOT caught here and can still skew accuracy toward a false regression; only
    a TOTAL collapse is detectable without per-call error visibility."""
    return m.n > 0 and (m.true_match + m.false_match) == 0


def format_human(m: JudgeMetrics) -> str:
    """Two-line human view. leniency = false_match_rate, strictness = false_no_match_rate —
    surfacing both axes so the DIRECTION of a regression is visible."""
    return (
        f"Judge accuracy={m.accuracy:.3f} (n={m.n})  "
        f"leniency={m.false_match_rate:.2f} strictness={m.false_no_match_rate:.2f}\n"
        f"  confusion: TM={m.true_match} TNM={m.true_no_match} "
        f"FM={m.false_match} FNM={m.false_no_match}"
    )


def gate_exit_code(m: JudgeMetrics, check: float | None) -> int:
    """0 if no gate or accuracy >= threshold (inclusive, matching the integration floor
    `accuracy >= ACCURACY_FLOOR`); 1 if the gate fired — the routing regression signal."""
    if check is None:
        return 0
    return 0 if m.accuracy >= check else 1


def emit(m: JudgeMetrics, *, as_json: bool) -> None:
    """The metrics line on STDOUT: one JSON line (asdict over the frozen dataclass — every
    field, no hand-typed keys) or the human view. stdout carries ONLY this (diagnostics go to
    stderr) so `--json` stays a single jq-parseable line."""
    print(json.dumps(asdict(m)) if as_json else format_human(m))


def _confirm_billing(n_calls: int, *, yes: bool) -> bool:
    """Make the billed run explicit. Auto-proceed when non-interactive (CI never hangs);
    otherwise require y/yes. The call count is real — no fabricated dollar figure."""
    print(f"[cost] score-judge runs {n_calls} real billed judge calls.", file=sys.stderr)
    if yes or not sys.stdin.isatty():
        return True
    print("  Proceed? [y/N] ", end="", file=sys.stderr, flush=True)
    return sys.stdin.readline().strip().lower() in {"y", "yes"}


def run_score_judge(*, model: str | None, check: float | None, as_json: bool, yes: bool) -> int:
    """`score-judge` entrypoint; returns the exit code (0=pass / 1=regression / 2=outage).

    Pre-flights the credential BEFORE constructing the client: make_judge degrades every
    per-pair API error to NO_MATCH (judge.py), so a missing/invalid key would NOT raise — it
    would silently yield all-NO_MATCH verdicts and a plausible accuracy, then route as a
    regression. The pre-flight (missing credential) and the post-run total-degradation guard
    (invalid credential) both convert that into a deterministic exit 2, and the pre-flight
    also forecloses an interactive macOS keychain prompt in CI. (The judge authenticates via
    the anthropic SDK — ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN — NOT the
    CLAUDE_CODE_OAUTH_TOKEN used for the headless /hydra subprocess, which the SDK ignores.)
    """
    if not has_anthropic_credential():
        print(
            "[ERROR] no anthropic credential (set ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN) "
            "— score-judge makes REAL billed judge calls via the anthropic SDK.",
            file=sys.stderr,
        )
        return 2

    try:
        from anthropic import Anthropic
    except ImportError:
        print(
            "[ERROR] anthropic SDK not installed (pip install 'anthropic>=0.96,<1.0').",
            file=sys.stderr,
        )
        return 2

    try:
        pairs = load_gold_set()  # load first so the billing note states the exact call count
    except (OSError, ValueError) as exc:  # missing/unreadable file or a corrupt JSON line
        print(
            f"[ERROR] gold-set unavailable ({exc}) — harness outage, not a regression.",
            file=sys.stderr,
        )
        return 2
    if not pairs:
        print("[ERROR] gold-set is empty — harness outage, not a regression.", file=sys.stderr)
        return 2

    if not _confirm_billing(len(pairs), yes=yes):
        print("[ERROR] billing not confirmed — aborted.", file=sys.stderr)
        return 2

    # make_judge, NOT resolve_judge: a score-judge tool must never silently no-op on
    # JUDGE_ENABLED=0. Anthropic() reads the credential pre-flighted above.
    from bench.runner.judge import make_judge

    judge = make_judge(client=Anthropic(), model=resolve_model(model))
    metrics = evaluate_judge(judge, pairs)
    emit(metrics, as_json=as_json)
    if is_total_judge_outage(metrics):
        print(
            "[ERROR] judge produced zero MATCH verdicts across the gold-set — almost certainly "
            "a degraded/auth-rejected run (e.g. an invalid key), not a real regression.",
            file=sys.stderr,
        )
        return 2
    return gate_exit_code(metrics, check)
