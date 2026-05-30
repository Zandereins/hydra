#!/usr/bin/env bash
# Launch the resumable P6 calibrated capture for cases 05-08.
#
# Resume-safe: cases already at n_scored>=5 in the baseline (01-04) are skipped; only 05-08
# are captured. Plan-billed, multi-hour. If a plan rate-limit or any interruption stops it,
# JUST RE-RUN THIS SCRIPT — it continues from the last completed case (per-case persistence).
set -euo pipefail

SKILL_DIR="$HOME/.claude/skills/hydra"
cd "$SKILL_DIR" 2>/dev/null || { echo "FATAL: run from $SKILL_DIR"; exit 1; }

# --- token: env first, then the optional file (mirrors the in-code fail-fast requirement) ---
if [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] && [ -f "$HOME/.claude/hydra-bench-oauth.env" ]; then
  CLAUDE_CODE_OAUTH_TOKEN="$(cat "$HOME/.claude/hydra-bench-oauth.env")"
  export CLAUDE_CODE_OAUTH_TOKEN
fi
[ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] || {
  echo "FATAL: CLAUDE_CODE_OAUTH_TOKEN not set. Run 'claude setup-token' first (see setup-remote.sh)."; exit 1; }

BASELINE="bench/baselines/hydra-ci-baseline-2026-05-29.json"
[ -f "$BASELINE" ] || { echo "FATAL: $BASELINE missing — without it the run captures all 8 cases."; exit 1; }

TS="$(date -u +%Y%m%dT%H%M%S)"
LOG="capture-remote-${TS}.log"

echo "Credit-safety reminder: '/usage-credits 0' must be set (account-level) so a rate-limit"
echo "exits free instead of drawing credits. Launching capture (nohup) -> $LOG"

# JUDGE_ENABLED=0: keyword-only canonical capture (the judge would run in THIS parent process
# with the key -> API-billed + non-reproducible). -u: unbuffered so the run-log is live.
JUDGE_ENABLED=0 nohup ./.venv/bin/python -u -m bench.runner.run_bench bench \
  --mode calibrate --baseline-out "$BASELINE" > "$LOG" 2>&1 &

PID=$!
echo "Launched PID $PID."
echo "  Monitor:  tail -f $SKILL_DIR/$LOG     (expect '[resume] skip 01..04', then 05-08 scoring)"
echo "  Resume:   if it stops (rate-limit/crash), just re-run this script."
echo "  Done when the baseline shows 8 cases x n_scored=5 (see REMOTE-CAPTURE.md, 'On completion')."
