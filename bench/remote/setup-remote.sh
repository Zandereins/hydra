#!/usr/bin/env bash
# Prepare a remote box to run the Hydra P6 calibrated capture for cases 05-08.
#
# Run this FROM INSIDE the cloned repo, which must live at ~/.claude/skills/hydra
# so that `claude --print /hydra` resolves the skill from the same checkout:
#
#   git clone https://github.com/Zandereins/hydra.git ~/.claude/skills/hydra
#   cd ~/.claude/skills/hydra && git checkout main
#   bash bench/remote/setup-remote.sh
#
# Idempotent: safe to re-run (it pulls, rebuilds the venv only if missing).
set -euo pipefail

SKILL_DIR="$HOME/.claude/skills/hydra"
cd "$SKILL_DIR" 2>/dev/null || { echo "FATAL: run from $SKILL_DIR (clone the repo there first)"; exit 1; }

echo "[1/5] Preconditions"
command -v git >/dev/null    || { echo "FATAL: install git"; exit 1; }
PY="$(command -v python3.12 || command -v python3 || true)"
[ -n "$PY" ]                 || { echo "FATAL: install Python >=3.12.3"; exit 1; }
"$PY" -c 'import sys; sys.exit(0 if sys.version_info[:3] >= (3,12,3) else 1)' \
                             || { echo "FATAL: Python >=3.12.3 required (have $($PY -V))"; exit 1; }
command -v claude >/dev/null || { echo "FATAL: install Claude Code CLI so 'claude' is on PATH"; exit 1; }

echo "[2/5] Sync repo (skill + bench must match)"
git pull --ff-only --quiet || echo "  (no fast-forward; staying on current commit)"

echo "[3/5] venv + deps (core + bench; the judge extra is NOT needed — calibrate is keyword-only)"
[ -d .venv ] || "$PY" -m venv .venv
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -e '.[bench]'

echo "[4/5] Resume baseline (cases 01-04 must already be 5/5 so only 05-08 are captured)"
BL="bench/baselines/hydra-ci-baseline-2026-05-29.json"
if [ -f "$BL" ]; then
  ./.venv/bin/python -c "import json;d=json.load(open('$BL'));print('  present:', {k:c.get('n_scored') for k,c in sorted(d.get('cases',{}).items())})"
else
  echo "  WARNING: $BL missing — capture would start from scratch (all 8 cases). Get the checkpoint onto this box."
fi

echo "[5/5] Auth (the headless /hydra subprocess fail-fasts without this token)"
if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
  echo "  CLAUDE_CODE_OAUTH_TOKEN: set in env."
elif [ -f "$HOME/.claude/hydra-bench-oauth.env" ]; then
  echo "  Token file ~/.claude/hydra-bench-oauth.env present (run-capture.sh will source it)."
else
  echo "  NOT set. Run 'claude setup-token' (interactive, plan-billed, revocable), then EITHER:"
  echo "    export CLAUDE_CODE_OAUTH_TOKEN=<token>"
  echo "    # or persist it:  umask 077; printf %s '<token>' > ~/.claude/hydra-bench-oauth.env"
fi

echo
echo "Setup OK. Before launching, confirm credit-safety once (account-level):"
echo "  in an interactive 'claude' session run  /usage-credits 0"
echo "  -> a plan rate-limit then EXITS cleanly (free) and you re-run to resume, instead of"
echo "     drawing euro credits. Then launch:  bash bench/remote/run-capture.sh"
