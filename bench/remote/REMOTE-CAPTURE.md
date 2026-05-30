# Remote P6 capture — cases 05-08

Finish the P6 calibrated baseline on a remote box instead of the local laptop (which
hard-freezes under the multi-hour load). Cases **01-04 are already captured (5/5)** and
shipped as a committed checkpoint; this run captures only **05-08** and resumes after any
interruption. When 8/8 land, the CI gate moves from **advisory** to **blocking**.

## Why remote
A full calibrate run is ~20 `/hydra` invocations (4 cases × 5 runs), plan-billed, multi-hour.
Running it off the interactive laptop removes the freeze/force-restart risk and frees the
machine. The capture is resume-safe (per-case persistence), so rate-limit windows are fine.

## Prerequisites on the box
- Linux (or macOS), `git`, **Python ≥ 3.12.3**, Node.js
- **Claude Code CLI** installed so `claude` is on `PATH`
  (`npm install -g @anthropic-ai/claude-code`, or the official installer)
- Same Anthropic subscription/account as locally (the OAuth token is plan-billed, inference-only)

## One-time setup
```bash
# 1. Clone the repo INTO the skill path (so `claude --print /hydra` resolves from it)
git clone https://github.com/Zandereins/hydra.git ~/.claude/skills/hydra
cd ~/.claude/skills/hydra && git checkout main      # the checkpoint baseline + these scripts are on main

# 2. Auth — interactive, needs a TTY (do it yourself, not via a wrapper)
claude setup-token                                  # 1-yr, subscription-billed, inference-only, revocable
umask 077; printf %s '<paste-token>' > ~/.claude/hydra-bench-oauth.env   # or: export CLAUDE_CODE_OAUTH_TOKEN=<token>

# 3. Credit-safety (account-level, ONCE) — so a plan rate-limit exits free, not on euro credits
claude            # interactive, then run:  /usage-credits 0

# 4. Build venv + deps + sanity checks
bash bench/remote/setup-remote.sh
```

## Run
```bash
bash bench/remote/run-capture.sh
```
It launches the capture under `nohup` and prints the PID + log path. Safe to disconnect.

## Monitor
```bash
tail -f ~/.claude/skills/hydra/capture-remote-*.log
```
Expect `[resume] skip 01-axios… / 02… / 03… / 04…`, then 05-08 scoring. Run-logs are
gitignored (`*.log`). Stdout telemetry (success-rate / failure-modes) lands here too.

## Resume
If the run stops (plan rate-limit → non-zero exit, or any crash), **just re-run**
`bash bench/remote/run-capture.sh`. It skips every case already at `n_scored>=5` and
continues. No state to clean up.

## On completion (8/8 at 5/5)
1. Sanity-check the baseline:
   ```bash
   ./.venv/bin/python -c "import json;d=json.load(open('bench/baselines/hydra-ci-baseline-2026-05-29.json'));\
   print({k:c.get('n_scored') for k,c in sorted(d['cases'].items())})"
   ```
   Expect all 8 cases at `5`, and the Wilson `critical_recall` CIs non-degenerate (not `[0,1]`).
2. Commit the **completed** baseline (this overwrites the partial checkpoint) on a branch →
   PR → merge. Then flip the gate from advisory to blocking (it auto-detects a multi-run
   baseline; see `gate_against_baseline` in `bench/runner/run_bench.py`).
3. To get the file off the box: `git add -f bench/baselines/hydra-ci-baseline-2026-05-29.json`
   on a branch and push, or `scp` it back.

## Notes
- `--mode calibrate` is **standard mode** → no Codex needed (calibrate never uses deep-mode advisors).
- `JUDGE_ENABLED=0` is mandatory for the canonical capture (the judge would otherwise run in
  the parent process with the key — API-billed + non-reproducible). The scripts set it.
- The capture writes to `bench/baselines/hydra-ci-baseline-2026-05-29.json` in the working
  tree; that's an uncommitted change on the box until you commit the finished 8/8 file.
