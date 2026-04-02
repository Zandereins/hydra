---
name: hydra
description: >
  Multi-perspective code review council: advisors analyze, reviewers
  cross-examine, chairman synthesizes verdict.
  USE for: architecture decisions, security audits, tradeoff analysis,
  "what am I missing" questions, pre-merge deep reviews, iterative
  re-reviews after fixes.
  DO NOT USE for: simple code generation, syntax fixes, single-file
  refactors, or factual lookups.
  TRIGGERS: 'hydra', 'hydra this', 'hydra review', 'run hydra',
  'hydra lite', 'Hydra starten',
  'hydra iterate', 'hydra re-review', 'hydra follow-up',
  'hydra history'.
---

# Hydra

Six independent advisors analyze your code from fundamentally different angles. Five
reviewers cross-examine their work. A chairman synthesizes a final verdict.

Four advisors run on Claude Opus. Two run on Codex GPT-5.4 — different model, different
training data, different blind spots. Three reviewers run on Opus, two on Codex.

Reference files in `references/` define all prompts and protocols — read them at the
relevant step.

---

## Modes

| Preset | CLI | Advisors | Reviewers | Chairman | Total |
|--------|-----|----------|-----------|----------|-------|
| **full** | *(default)* | 6 (4 Opus + 2 Codex) | 5 (3 Opus + 2 Codex) | 1 Opus | 12 |
| **lean** | `--no-review` | 6 (4 Opus + 2 Codex) | 0 | 1 Opus | 7 |
| **private** | `--no-codex` | 6 (all Opus) | 3 (Opus only) | 1 Opus | 10 |
| **stealth** | `--no-review --no-codex` | 6 (all Opus) | 0 | 1 Opus | 7 |
| **lite** | `--mode lite` | 3 (Cassandra + Mies + Navigator) | 0 | 1 Opus | 4 |

**Minimum thresholds** — formula: `ceil(N × 0.6)`, min 2:

| Preset | Min Advisors | Min Reviewers |
|--------|-------------|---------------|
| full | 4 of 6 | 3 of 5 |
| lean | 4 of 6 | — |
| private | 4 of 6 | 2 of 3 |
| stealth | 4 of 6 | — |
| lite | 2 of 3 | — |

**Mode resolution:** Flags resolve to presets deterministically:
- `--no-review` alone → **lean**
- `--no-codex` alone → **private**
- `--no-review --no-codex` → **stealth**
- `--mode lite` → **lite** (ignores other flags with warning)
- No flags → **full**

---

## How a Hydra Session Works

### Step 0: Pre-flight Gate

1. **Concrete code or specific decision?** If too vague, ask ONE clarifying question.
2. **Hydra-worthy?** Simple questions get answered directly: `[Hydra] Not Hydra-worthy — answering directly.`
3. **Input size check:** If user code exceeds ~500 lines, ask user to highlight the critical section. Max enriched input: ~3000 tokens of source code.
4. **Secrets scan:** Check for credentials using these patterns:
   Cloud keys: `AKIA[A-Z0-9]{16}`, `ASIA[A-Z0-9]{16}`,
   Git/CI: `ghp_...`, `github_pat_...`, `glpat-...`,
   Slack: `xox[bpsa]-...`, `https://hooks.slack.com/...`,
   Stripe: `sk_live_`, `sk_test_`, `pk_live_`, `rk_live_`, `rk_test_`, `whsec_`,
   AI keys: `sk-ant-`, `sk-proj-`, `AIzaSy`,
   PEM: `-----BEGIN.*PRIVATE.*KEY-----`, `-----BEGIN.*KEY-----`,
   JWT: `eyJhbG...eyJ` (require header.payload, not just header prefix),
   DB strings: `(mongodb|postgres|mysql|redis)://[^:]+:[^@]+@`,
   Other: `AccountKey=`, `SG\.[a-zA-Z0-9_-]{22}\.`, `.env` contents.
   Replace matches with `[REDACTED-{HEX6}]` where HEX6 = first 6 chars of HYDRA_BOUNDARY.
   All redactions use the SAME opaque marker — no type information leaks to agents.
   Orchestrator keeps internal mapping for user-facing reports only.
   If secrets found: show redacted locations and ask user to confirm before proceeding.

   **Scan procedure name: `secrets-scan`** — referenced by scan points in Steps 3-6.
5. **Iteration detection** (skip if fresh review):
   ```bash
   ls -1t .hydra/reports/hydra-*.md 2>/dev/null | grep -v transcript | head -1
   ```
   If trigger is an iterate-trigger (`hydra iterate`, `re-review`, `check my fixes`, etc.)
   AND a previous report exists: set `HYDRA_ITERATE=true`, extract Top Actions + Verdict
   lead + timestamp from the report. Default to `--mode lite` unless user passes `--mode full`.
   Print: `[Hydra] Iterating on: {{PREV_REPORT}} ({{AGE}} ago)`
   If no previous report exists: warn user, fall back to fresh review.

   **Report validation:** If a previous report IS found, verify it contains:
   - `**Top Actions:**` block with at least one numbered item (required)
   - Timestamp in filename matching `hydra-[0-9]{8}T[0-9]{6}-*.md` (required)
   - `## Verdict` heading with content below it (recommended but not required —
     chairman-failure reports may lack a verdict but still contain actionable findings)
   If Top Actions AND timestamp are missing: report is invalid, fall back to fresh review.
   If only Verdict is missing: proceed with iteration using available data, note degraded context.

   **State file (preferred):** If `.hydra/state.json` exists, use it instead of parsing
   the markdown report. Schema: `{version: 1, latest: {report_path, timestamp_unix,
   top_actions[], verdict_lead, mode, reviewed_files[]}}`. Written by Step 6 after each
   successful review. Falls back to `ls -1t` + markdown parsing if state.json is absent.
6. **Generate boundary token** for delimiter security:
   ```bash
   HYDRA_BOUNDARY="HYDRA-$(openssl rand -hex 6)"
   ```
   If `openssl` is unavailable: `HYDRA_BOUNDARY="HYDRA-$(head -c 6 /dev/urandom | xxd -p)"`.
   If both fail: abort with `[Hydra] Cannot generate secure boundary token. Aborting.`

   Store the result (e.g., `HYDRA-a3f7c9e1b042`) — you will interpolate it as
   `{{BOUNDARY}}` into all advisor preambles (Step 3) and reviewer delimiters (Step 4).
   This prevents user code or advisor output from escaping data delimiters.

   **Prompt Assembly Rule** (applies to Steps 3, 4, 5):
   When building ANY prompt for an agent (advisor, reviewer, chairman):
   1. Write the instruction/template portion. Replace all `{{...}}` placeholders with resolved values.
   2. Verify: the resolved instruction portion contains ZERO `{{...}}` placeholders.
   3. Append untrusted content (user code, advisor responses, reviewer responses) as verbatim
      text after the resolved instructions. Never apply placeholder substitution to untrusted content.
   This two-pass rule prevents user code containing `{{BOUNDARY}}` from being replaced with the real token.

7. **Codex check** (skip if `--no-codex` or `--mode lite`):
   ```bash
   CODEX_SCRIPT=$(ls -1t ~/.claude/plugins/cache/openai-codex/codex/*/scripts/codex-companion.mjs 2>/dev/null | head -1)
   ```
   If empty or file doesn't exist: auto-switch to `--no-codex`, inform user.
   Store the resolved path as `CODEX_SCRIPT_PATH` — hardcode it in Step 3/4 Bash calls
   (shell state does not persist between tool calls).
8. **Classify question type** (uses final resolved mode from steps 5+7): `CODE_REVIEW` | `ARCHITECTURE_DECISION` | `SECURITY_AUDIT` | `DEBUGGING` | `GENERAL_TECHNICAL`
   If `SECURITY_AUDIT` and `--mode lite`: warn user — `Lite mode excludes Sentinel (security specialist). Consider full mode or --no-review. Proceed anyway? [Y/n]`
9. **Cost warning + confirmation:**

```
Hydra: {{AGENT_COUNT}} agents. {{PROVIDER_NOTE}}.
Estimated: {{TIME}}, {{COST}}.

Alternatives:
  --mode lite     → 4 agents, ~$0.50-1.50, ~1 min (3 Opus advisors, no review)
  --no-review     → lean: 7 agents, ~$2, ~1.5 min (no review)
  --no-codex      → private: 10 agents, ~$3-4, ~2 min (Opus only)
  --no-review --no-codex → stealth: 7 agents, ~$1-2, ~1 min (Opus only, no review)

Proceed? [Y/n/lite]
```

Provider note: Full mode → `Code sent to Claude (Anthropic) + Codex (OpenAI). Use --no-codex to keep code Anthropic-only.`
Opus-only modes → `Code sent to Claude (Anthropic) only.`

### Step 1: Context Enrichment

Quickly scan (< 30 seconds):
- `CLAUDE.md` in project root (use cwd as root if not a git repo)
- Source files the user referenced
- `git diff`, `git log --oneline -5` (skip if not a git repo)
- Project structure (high-level)

**Hard limit: 5000 tokens.** Priority: source code > git diff > CLAUDE.md > project structure.
If `HYDRA_ITERATE`: use `git diff` since previous report timestamp instead of full diff.
Add previous Top Actions (~100 tokens) to enriched context.
Apply secrets scan to enriched context.

### Step 2: Frame the Question

```
QUESTION: [core decision or review request]
CONTEXT: [key context from user + enriched files]
QUESTION TYPE: [classification]
STAKES: [why this decision matters]
```

If `HYDRA_ITERATE`, append to the framed question:

```
ITERATION CONTEXT:
Previous review: {{PREV_REPORT}} ({{AGE}} ago)
Previous Top Actions:
{{TOP_ACTIONS_FROM_PREV_REPORT}}
Changes since: {{GIT_DIFF_STAT_SUMMARY}}
TASK: Re-review — verify fixes and assess remaining/new issues.
```

### Step 3: Spawn Advisors (parallel)

Read `references/advisors.md`. It defines a Common Preamble (shared by all advisors)
and each advisor's unique prompt. Interpolate `{{FRAMED_QUESTION}}`,
`{{ENRICHED_CONTEXT}}`, and `{{BOUNDARY}}` (the token from Step 0) into the Common
Preamble, then append each advisor's unique section.

**Which advisors** — see Modes table above. In private/stealth mode, Stranger and Sentinel
run as Opus agents (same prompts, spawn via Agent tool instead of Codex). All 6
perspectives are preserved; only cross-model diversity is lost.

   **Stranger context restriction:** For The Stranger, omit CLAUDE.md and project structure
   from the enriched context. Provide only source code and git diff. This preserves the
   Stranger's "zero context first-reader" design.

**Opus Advisors:** Spawn via Agent tool with `model: "opus"`.

**Codex Advisors** (full and no-review modes only).
Send the ENTIRE block below as ONE Bash tool call (shell state does not persist
between calls — PID variables, traps, and background jobs require a single shell):

First create the temp dir (separate Bash call), then write prompt files via Write tool,
then send the Codex block as ONE Bash call:

```bash
# Step A (separate Bash call): create temp dir, store path
HYDRA_TMP=$(mktemp -d /tmp/hydra-XXXXXX) && echo "$HYDRA_TMP"
```

Set Bash tool timeout parameter to `150000` (150s). Internal timer at 100s ensures cleanup runs before the tool timeout. Uses `pkill -P` (macOS-compatible) to kill process trees, not just parent PIDs.

```bash
# Step B (ONE Bash call — set Bash tool timeout to 150000ms):
HYDRA_TMP="{{HYDRA_TMP_PATH}}"
CODEX="{{CODEX_SCRIPT_PATH}}"
trap 'pkill -P $$ 2>/dev/null; rm -rf "$HYDRA_TMP"' EXIT INT TERM

node "$CODEX" task --prompt-file "$HYDRA_TMP/prompt-stranger.md" \
  > "$HYDRA_TMP/output-stranger.txt" 2>"$HYDRA_TMP/stderr-stranger.txt" &
PID1=$!
node "$CODEX" task --prompt-file "$HYDRA_TMP/prompt-sentinel.md" \
  > "$HYDRA_TMP/output-sentinel.txt" 2>"$HYDRA_TMP/stderr-sentinel.txt" &
PID2=$!

# Timer: 100s internal (50s buffer before 150s Bash tool timeout)
( sleep 100; for P in $PID1 $PID2; do pkill -P "$P" 2>/dev/null; kill "$P" 2>/dev/null; done ) &
TIMER=$!
wait $PID1 2>/dev/null; EXIT1=$?
wait $PID2 2>/dev/null; EXIT2=$?
kill $TIMER 2>/dev/null; wait $TIMER 2>/dev/null
echo "STRANGER_EXIT=$EXIT1 SENTINEL_EXIT=$EXIT2"
```

Use the same pattern for Codex reviewers (4-5) in Step 4.

Use `--prompt-file` only — no positional args (tokenizer breaks quoted prompts),
no codex-rescue subagent.

All advisors in parallel. Print: `[Hydra] Advisors spawned ({{N}}). Waiting...`
As each completes: `[Hydra] {{Name}} done ({{M}}/{{N}})`

After each advisor completes, validate the response structurally:
- **Valid response** must contain: (a) a `POSITION: APPROVE|CONCERN|REJECT` line,
  (b) at least one advisor-specific finding field OR an explicit "no findings"/"no issues"
  statement, and (c) at least 3 lines of substantive content (excluding blank lines), OR the response
  contains an explicit "no findings"/"no issues" statement (short valid responses are
  acceptable when the advisor found nothing to report).
- If response fails ALL of (a), (b), (c): treat as invalid. Mark as `[INVALID — missing POSITION/fields]`.
- If response is completely empty or ≤2 lines without "no findings": treat as timeout.
**Timeout: 120 seconds per advisor.**

**Scan:** Run secrets-scan (Step 0.4) on each advisor output. Silent redact.

**Persist advisor outputs:** Write each advisor's response to
   `$HYDRA_TMP/advisor-{name}.md` immediately after completion. If the session is
   interrupted before the report, these files can be recovered from the temp directory.

**Codex cascade check:** If both Codex advisors (Stranger + Sentinel) fail or are
invalid, auto-switch to `--no-codex` for the reviewer phase. Print:
`[Hydra] Both Codex advisors failed. Switching to Opus-only for reviewers.`
If only one Codex advisor fails: proceed normally, count toward minimum.
If failure reason is auth error (401/403) or script-not-found: switch immediately
even on a single failure (not transient).

### Step 4: Peer Review (parallel)

**Skip entirely** if mode has no review phase (lean, stealth, lite).

Read `references/review-protocol.md` for the full protocol.

1. Collect all advisor responses. Label and wrap per `references/review-protocol.md`.
2. Spawn reviewers in parallel:
   - **Full mode:** 3 Opus (reviewers 1-3) + 2 Codex (reviewers 4-5)
   - **No-Codex mode:** 3 Opus only (reviewers 1-3)

Print: `[Hydra] Peer review started ({{N}} reviewers)...`
As each reviewer completes: `[Hydra] Reviewer {{N}} done ({{M}}/{{TOTAL}})`
**Timeout: 120 seconds per reviewer.**

**Scan:** Run secrets-scan on each reviewer output. Silent redact.

### Step 5: Chairman Synthesis

Read `references/chairman-protocol.md` for the protocol and verdict formats.

Spawn 1 Opus agent. Adapt the chairman prompt per the MODE ADAPTATION rules in `references/chairman-protocol.md`.

If `HYDRA_ITERATE`: append to the chairman prompt before RULES:

```
ITERATION MODE — This is a follow-up review. Previous Top Actions:
{{TOP_ACTIONS_FROM_PREV_REPORT}}
After the verdict, produce a DELTA BLOCK (outside word limit, max 150 words):
**Fixed:** [previous actions now resolved, with evidence]
**Remaining:** [previous actions still present]
**New:** [findings not in previous review]
**Progress:** [X of Y previous actions addressed]
```

**Scan:** Run secrets-scan on chairman output. Silent redact.

### Step 6: Generate Report

Read `references/report-template.md` for the template. Generate inline (no extra agent).

**Final scan:** Run secrets-scan on assembled report before disk write. If findings: redact and append note. If --transcript: scan transcript file too.

**Save to:** `.hydra/reports/hydra-YYYYMMDDTHHMMSS-{slug}.md`
Slug: derive from the first 3-4 words of the title via Bash:
```bash
SLUG=$(echo "first three words" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g' | sed 's/--*/-/g' | head -c 40 | sed 's/-$//')
```
Run this command; do not generate the slug by string manipulation in your response.
If slug is empty after sanitization, use `review`.
Create `.hydra/` dir and `.hydra/.gitignore` with `*` on first run (`mkdir -p .hydra/reports`).

   **Write state file:** After saving the report, write `.hydra/state.json`:
   ```json
   {
     "version": 1,
     "latest": {
       "report_path": ".hydra/reports/hydra-{TIMESTAMP}-{SLUG}.md",
       "timestamp_unix": {UNIX_EPOCH},
       "top_actions": ["action 1", "action 2", ...],
       "verdict_lead": "first 2-3 sentences of verdict",
       "mode": "{PRESET_NAME}",
       "reviewed_files": ["path/to/file1", ...]
     }
   }
   ```
   Extract `top_actions` from chairman's SUMMARY BLOCK. Extract `reviewed_files` from
   file paths mentioned in advisor responses. If state.json write fails: warn, continue
   (the report is the primary artifact; state.json is an optimization).

   **Reviewer Highlights:** Extract the Comparative Analysis (Part 2) from each reviewer.
   Synthesize into the Reviewer Highlights section: strongest/weakest advisor (by reviewer
   consensus), shared blind spots, devil's advocate highlight. Max 150 words. The orchestrator
   produces this section — not the chairman. If no reviewers ran, omit the section.

Omit sections for advisors/reviewers that didn't participate in this mode (don't list
them as timeout). For actual timeouts: mark as `[TIMEOUT — no response]`.
Omit `## Peer Reviews` if no reviewers ran. Omit `### Cross-Model Signals` if Opus-only.
If fewer than expected responded, add degradation note at top of Verdict section.

If `--transcript`: save raw agent outputs to separate file (see report-template.md).

### Step 7: Present Results

Present in-conversation summary (max 25 lines) using the chairman's SUMMARY BLOCK,
formatted per `references/report-template.md`.

If `HYDRA_ITERATE`, use the chairman's DELTA BLOCK instead:

```
## Hydra Delta: {{TITLE}}

**Progress: {{X}}/{{Y}} previous actions addressed**

**Fixed:** {{resolved actions}}
**Remaining:** {{unresolved actions}}
**New Issues:** {{new findings, if any}}

**Next Step:** {{ONE action}}

Full report: `.hydra/reports/hydra-{{TIMESTAMP}}-{{SLUG}}.md`
Previous: `{{PREV_REPORT}}`
```

---

## Error Handling

| Failure | Action |
|---------|--------|
| 0 advisors respond | `[Hydra] ABORTED: 0/N advisors responded. Likely API/network issue. Try again.` |
| Below min advisors | `[Hydra] ABORTED: Only N/M responded (list names). Try: --no-codex or --mode lite` |
| Below min reviewers | Proceed with degraded confidence note in verdict and report. |
| Chairman fails | Generate report without verdict — include Consensus Map + raw advisor outputs. |
| Codex script not found | Auto-switch to `--no-codex`. Note in report. |
| Codex task fails | Skip advisor, count toward minimum. Check `$HYDRA_TMP/stderr-*.txt` for diagnostics. |
| Report write fails | Dump full report inline in conversation as fallback. |
| Secrets in context | Auto-redact, show locations, ask user before proceeding. |
| Both Codex advisors fail | Auto-switch to `--no-codex` for reviewers. `[Hydra] Both Codex advisors failed. Switching to Opus-only.` |
| Malformed advisor response | Treat as failure (not timeout). Advisor must contain `POSITION:` line + ≥3 substantive lines. |
| Concurrent Hydra run | Warn if recent `/tmp/hydra-*` dirs exist (< 5 min). Don't block. |
| Bash timeout race | Internal timer (100s) < Bash tool timeout (150s). 50s buffer ensures trap runs. |

---

## History Command

Trigger: `hydra history`. No agents spawned, no cost.

```bash
ls -1t .hydra/reports/hydra-*.md 2>/dev/null | grep -v transcript | head -20
```

Present as table: `| # | Date | Title | Report Path |`
Extract date from filename (`hydra-YYYYMMDDTHHMMSS-slug.md`), title from first H1.
If no reports: `[Hydra] No reviews found. Run 'hydra this' to start.`
