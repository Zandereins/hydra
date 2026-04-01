---
name: hydra
description: >
  Multi-perspective code review council: advisors analyze, reviewers
  cross-examine, chairman synthesizes verdict.
  USE for: architecture decisions, security audits, tradeoff analysis,
  "what am I missing" questions, pre-merge deep reviews.
  DO NOT USE for: simple code generation, syntax fixes, single-file
  refactors, or factual lookups.
  TRIGGERS: 'hydra', 'hydra this', 'hydra review', 'run hydra',
  'hydra lite', 'Hydra starten', 'red team this',
  'tear this apart', 'stress test this', 'roast this code',
  'what am I missing', 'second opinion', 'blind spots',
  'check my blind spots', 'is this overengineered', 'sanity check this',
  'hydra iterate', 'hydra re-review', 'did I fix the issues',
  'hydra follow-up', 'check my fixes', 'run hydra again'.
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

| Mode | Flag | Advisors | Reviewers | Chairman | Total |
|------|------|----------|-----------|----------|-------|
| Full | *(default)* | 6 (4 Opus + 2 Codex) | 5 (3 Opus + 2 Codex) | 1 Opus | 12 |
| No-Review | `--no-review` | 6 (4 Opus + 2 Codex) | 0 | 1 Opus | 7 |
| No-Codex | `--no-codex` | 6 (all Opus) | 3 (Opus only) | 1 Opus | 10 |
| Lite | `--mode lite` | 3 (Cassandra + Mies + Navigator) | 0 | 1 Opus | 4 |

**Minimum thresholds:**

| Mode | Min Advisors | Min Reviewers |
|------|-------------|---------------|
| Full | 4 of 6 | 3 of 5 |
| No-Review | 4 of 6 | — |
| No-Codex | 4 of 6 | 2 of 3 |
| Lite | 2 of 3 | — |

---

## How a Hydra Session Works

### Step 0: Pre-flight Gate

1. **Concrete code or specific decision?** If too vague, ask ONE clarifying question.
2. **Hydra-worthy?** Simple questions get answered directly: `[Hydra] Not Hydra-worthy — answering directly.`
3. **Input size check:** If user code exceeds ~500 lines, ask user to highlight the critical section. Max enriched input: ~3000 tokens of source code.
4. **Secrets scan:** Check for credentials using these patterns:
   `AKIA...`, `ghp_...`, `xox[bpsa]-...`, `sk_live_`, `pk_live_`,
   `-----BEGIN.*KEY-----`, `-----BEGIN.*PRIVATE KEY-----`, `eyJhbG` (JWT),
   `sk-ant-`, `sk-proj-`, `github_pat_`, `glpat-`, `AIzaSy`,
   `AccountKey=`, `://[^:]+:[^@]+@` (connection strings),
   `.env` contents.
   Replace matches with `[REDACTED:type]`. If secrets found: show redacted locations
   and ask user to confirm before proceeding.
5. **Iteration detection** (skip if fresh review):
   ```bash
   ls -1t .hydra/reports/hydra-*.md 2>/dev/null | grep -v transcript | head -1
   ```
   If trigger is an iterate-trigger (`hydra iterate`, `re-review`, `check my fixes`, etc.)
   AND a previous report exists: set `HYDRA_ITERATE=true`, extract Top Actions + Verdict
   lead + timestamp from the report. Default to `--mode lite` unless user passes `--mode full`.
   Print: `[Hydra] Iterating on: {{PREV_REPORT}} ({{AGE}} ago)`
   If no previous report exists: warn user, fall back to fresh review.
6. **Classify question type:** `CODE_REVIEW` | `ARCHITECTURE_DECISION` | `SECURITY_AUDIT` | `DEBUGGING` | `GENERAL_TECHNICAL`
   If `SECURITY_AUDIT` and `--mode lite`: warn user — `Lite mode excludes Sentinel (security specialist). Consider full mode or --no-review. Proceed anyway? [Y/n]`
6. **Codex check** (skip if `--no-codex` or `--mode lite`):
   ```bash
   CODEX_SCRIPT=$(ls -1t ~/.claude/plugins/cache/openai-codex/codex/*/scripts/codex-companion.mjs 2>/dev/null | head -1)
   ```
   If empty or file doesn't exist: auto-switch to `--no-codex`, inform user.
   Store the resolved path as `CODEX_SCRIPT_PATH` — hardcode it in Step 3/4 Bash calls
   (shell state does not persist between tool calls).
7. **Generate boundary token** for delimiter security:
   ```bash
   HYDRA_BOUNDARY="HYDRA-$(openssl rand -hex 6)"
   ```
   Store the result (e.g., `HYDRA-a3f7c9e1b042`) — you will interpolate it as
   `{{BOUNDARY}}` into all advisor preambles (Step 3) and reviewer delimiters (Step 4).
   This prevents user code or advisor output from escaping data delimiters.
8. **Cost warning + confirmation:**

```
Hydra: {{AGENT_COUNT}} agents. {{PROVIDER_NOTE}}.
Estimated: {{TIME}}, {{COST}}.

Alternatives:
  --mode lite  → 4 agents, ~$1.50-2, ~1 min (Opus only, no review)
  --no-review  → 7 agents, ~$2, ~1.5 min
  --no-codex   → 10 agents, ~$4, ~2 min (Opus only)

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

**Which advisors** — see Modes table above. In `--no-codex` mode, Stranger and Sentinel
run as Opus agents (same prompts, spawn via Agent tool instead of Codex). All 6
perspectives are preserved; only cross-model diversity is lost.

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

```bash
# Step B (ONE Bash call after prompt files are written):
HYDRA_TMP="{{HYDRA_TMP_PATH}}"
trap 'rm -rf "$HYDRA_TMP"' EXIT
CODEX="{{CODEX_SCRIPT_PATH}}"
# Spawn both Codex advisors in parallel
( node "$CODEX" task --prompt-file "$HYDRA_TMP/prompt-stranger.md" > "$HYDRA_TMP/output-stranger.txt" 2>"$HYDRA_TMP/stderr-stranger.txt" ) & PID1=$!
( node "$CODEX" task --prompt-file "$HYDRA_TMP/prompt-sentinel.md" > "$HYDRA_TMP/output-sentinel.txt" 2>"$HYDRA_TMP/stderr-sentinel.txt" ) & PID2=$!
( sleep 120 && kill $PID1 $PID2 2>/dev/null ) & TIMER=$!
wait $PID1 $PID2 2>/dev/null
kill $TIMER 2>/dev/null; wait $TIMER 2>/dev/null
```

Use the same pattern for Codex reviewers (4-5) in Step 4.

Use `--prompt-file` only — no positional args (tokenizer breaks quoted prompts),
no codex-rescue subagent.

All advisors in parallel. Print: `[Hydra] Advisors spawned ({{N}}). Waiting...`
As each completes: `[Hydra] {{Name}} done ({{M}}/{{N}})`

After each advisor completes: if output < 50 tokens and does NOT contain "no findings",
"no issues", or "no further findings", discard and treat as timeout.
**Timeout: 120 seconds per advisor.**

### Step 4: Peer Review (parallel)

**Skip entirely** if `--no-review` or `--mode lite`.

Read `references/review-protocol.md` for the full protocol.

1. Collect all advisor responses. Label and wrap per `references/review-protocol.md`.
2. Spawn reviewers in parallel:
   - **Full mode:** 3 Opus (reviewers 1-3) + 2 Codex (reviewers 4-5)
   - **No-Codex mode:** 3 Opus only (reviewers 1-3)

Print: `[Hydra] Peer review started ({{N}} reviewers)...`
**Timeout: 120 seconds per reviewer.**

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

### Step 6: Generate Report

Read `references/report-template.md` for the template. Generate inline (no extra agent).

**Save to:** `.hydra/reports/hydra-YYYYMMDDTHHMMSS-{slug}.md`
Slug: first 3-4 words, kebab-case. Sanitize: `[a-z0-9-]` only, max 40 chars.
If slug is empty after sanitization, use `review`. Create `.hydra/` dir and
`.hydra/.gitignore` with `*` on first run (`mkdir -p .hydra/reports`).

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
