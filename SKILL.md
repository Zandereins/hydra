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
  'hydra lite', 'hydra quick', 'hydra deep', 'Hydra starten',
  'hydra iterate', 'hydra re-review', 'hydra follow-up',
  'hydra history', 'hydra pr', 'hydra branch',
  'hydra ?', 'hydra auto', 'fix #'.
---

# Hydra

Six independent advisors analyze your code from fundamentally different angles. Three
reviewers cross-examine their work. A chairman synthesizes a final verdict.

Four advisors run on Claude Opus. Two run on Codex GPT-5.4 -- different model, different
training data, different blind spots. All three reviewers run on Opus.

Reference files in `references/` define all prompts and protocols -- read them at the
relevant step.

---

## Modes

| Preset | CLI | Aliases | Advisors | Reviewers | Chairman | Total |
|--------|-----|---------|----------|-----------|----------|-------|
| **full** | *(default)* | `deep`, `--mode deep` | 6 (4 Opus + 2 Codex) | 3 (all Opus) | 1 Opus | 10 |
| **lean** | `--no-review` | `broad`, `--mode broad` | 6 (4 Opus + 2 Codex) | 0 | 1 Opus | 7 |
| **private** | `--no-codex` | `secure`, `--mode secure` | 6 (all Opus) | 3 (all Opus) | 1 Opus | 10 |
| **stealth** | `--no-review --no-codex` | `focused`, `--mode focused` | 6 (all Opus) | 0 | 1 Opus | 7 |
| **lite** | `--mode lite` | `quick`, `--mode quick` | 3 (Cassandra + Stranger Codex/Opus + Sentinel Codex/Opus) | 0 | 1 Opus | 4 |

**Minimum thresholds** -- formula: `ceil(N * 0.6)`, min 2:

| Preset | Min Advisors | Min Reviewers |
|--------|-------------|---------------|
| full | 4 of 6 | 2 of 3 |
| lean | 4 of 6 | -- |
| private | 4 of 6 | 2 of 3 |
| stealth | 4 of 6 | -- |
| lite | 2 of 3 | -- |

**Mode resolution:** Flags resolve to presets deterministically:
- `--no-review` alone -> **lean**
- `--no-codex` alone -> **private**
- `--no-review --no-codex` -> **stealth**
- `--mode lite` or `--mode quick` -> **lite** (ignores other flags with warning)
- `--mode deep` -> **full**
- `--mode broad` -> **lean**
- `--mode secure` -> **private**
- `--mode focused` -> **stealth**
- No flags -> **full**

**Focus modes** (combinable with any preset): `--focus security | perf | readability | architecture | reliability`
When a focus flag is active, the primary advisor for that focus gets 2x word budget.
The chairman receives a focus directive weighting that advisor's findings at 1.5x.
Focus mapping: security -> Sentinel, perf -> Volta, readability -> Stranger, architecture -> Navigator, reliability -> Cassandra.

---

## How a Hydra Session Works

### Step 0: Pre-flight Gate

1. **Concrete code or specific decision?** If too vague, ask ONE clarifying question.
2. **Hydra-worthy?** Simple questions get answered directly: `[Hydra] Not Hydra-worthy -- answering directly.`
3. **Input size check:** If user code exceeds ~500 lines, ask user to highlight the critical section. Max enriched input: ~3000 tokens of source code.
4. **Secrets scan:** Check for credentials using these patterns:
   Cloud keys: `AKIA[A-Z0-9]{16}`, `ASIA[A-Z0-9]{16}`,
   Azure: `DefaultEndpointsProtocol=`, `AccountKey=[A-Za-z0-9+/=]{86,88}`, `SharedAccessSignature=`,
   GCP: `"type"\s*:\s*"service_account"`, `"private_key_id"\s*:\s*"[a-f0-9]{40}"`,
   Git/CI: `ghp_...`, `github_pat_...`, `glpat-...`,
   Slack: `xox[bpsa]-...`, `https://hooks.slack.com/...`,
   Stripe: `sk_live_`, `sk_test_`, `pk_live_`, `rk_live_`, `rk_test_`, `whsec_`,
   AI keys: `sk-ant-`, `sk-proj-`, `AIzaSy`,
   PEM: `-----BEGIN.*PRIVATE.*KEY-----`, `-----BEGIN.*KEY-----`,
   JWT: `eyJhbG...eyJ` (require header.payload, not just header prefix),
   DB strings: `(mongodb|postgres|mysql|redis)://[^:]+:[^@]+@`,
   Datadog: `DD_API_KEY`, `DD_APP_KEY`,
   Twilio: `AC[a-f0-9]{32}`, `SK[a-f0-9]{32}`,
   Other: `AccountKey=`, `SG\.[a-zA-Z0-9_-]{22}\.`, `.env` contents.
   Replace matches with `[REDACTED]`. Use a plain marker without any session-specific
   information -- do not derive the redaction marker from the boundary token or any other
   security-critical value. The marker is identical for all redactions in a session.
   Orchestrator keeps an internal count and mapping (type + location) for the user-facing
   confirmation only -- this mapping is never included in agent prompts.
   If secrets found: show redacted locations and ask user to confirm before proceeding.

   **Scan procedure name: `secrets-scan`** -- referenced by scan points in Steps 3-6.
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
   - `## Verdict` heading with content below it (recommended but not required)
   If Top Actions AND timestamp are missing: report is invalid, fall back to fresh review.

   **State file (preferred):** If `.hydra/state.json` exists, use it instead of parsing
   the markdown report. Schema: `{version: 2, latest: {report_path, timestamp_unix,
   top_actions[], verdict_lead, mode, reviewed_files[]}}`. Written by Step 6 after each
   successful review. Falls back to `ls -1t` + markdown parsing if state.json is absent.

   **State file version check:** If `version` field is missing or not equal to 2, warn
   user and fall back to markdown parsing. Do not silently use incompatible schema.
6. **Generate boundary tokens** for delimiter security:
   ```bash
   HYDRA_BASE="$(openssl rand -hex 6)"
   ```
   If `openssl` is unavailable: `HYDRA_BASE="$(head -c 6 /dev/urandom | xxd -p)"`.
   If both fail: abort with `[Hydra] Cannot generate secure boundary token. Aborting.`

   Derive per-stage tokens:
   - `HYDRA_BOUNDARY_A="HYDRA-${HYDRA_BASE}-A"` (advisor stage)
   - `HYDRA_BOUNDARY_R="HYDRA-${HYDRA_BASE}-R"` (reviewer stage)
   - `HYDRA_BOUNDARY_C="HYDRA-${HYDRA_BASE}-C"` (chairman stage)

   Use `{{BOUNDARY}}` = `HYDRA_BOUNDARY_A` in advisor preambles (Step 3).
   Use `{{BOUNDARY}}` = `HYDRA_BOUNDARY_R` in reviewer delimiters (Step 4).
   Use `{{BOUNDARY}}` = `HYDRA_BOUNDARY_C` in chairman delimiters (Step 5).
   This prevents advisor output from escaping reviewer/chairman delimiters.

   **Prompt Assembly Rule** (applies to Steps 3, 4, 5):
   When building ANY prompt for an agent (advisor, reviewer, chairman):
   1. Write the instruction/template portion. Replace all `{{...}}` placeholders with resolved values.
   2. Verify: the resolved instruction portion contains ZERO `{{...}}` placeholders.
   3. Append untrusted content (user code, advisor responses, reviewer responses) as verbatim
      text after the resolved instructions. Never apply placeholder substitution to untrusted content.
   This two-pass rule prevents user code containing `{{BOUNDARY}}` from being replaced with the real token.

7. **Codex check** (skip if `--no-codex`):
   ```bash
   CODEX_SCRIPT=$(ls -1t ~/.claude/plugins/cache/openai-codex/codex/*/scripts/codex-companion.mjs 2>/dev/null | head -1)
   ```
   If empty or file doesn't exist: auto-switch to `--no-codex`, inform user.
   Store the resolved path as `CODEX_SCRIPT_PATH` -- hardcode it in Step 3/4 Bash calls
   (shell state does not persist between tool calls).

   **Codex circuit breaker state:** Initialize `CODEX_FAILURES=0`. After each Codex call failure,
   increment. If `CODEX_FAILURES >= 2`: set `CODEX_CIRCUIT_OPEN=true`, skip all remaining Codex
   calls, switch to Opus for remaining agents. Print: `[Hydra] Codex circuit breaker open after
   {{N}} consecutive failures. Remaining agents run on Opus.`
8. **Classify question type** (uses final resolved mode from steps 5+7): `CODE_REVIEW` | `ARCHITECTURE_DECISION` | `SECURITY_AUDIT` | `DEBUGGING` | `GENERAL_TECHNICAL`
   If `SECURITY_AUDIT` and `--mode lite`: Sentinel is included. Proceed normally.
9. **Determine input complexity** for dynamic word limits:
   ```
   INPUT_SIZE = count lines of source code provided
   if INPUT_SIZE < 100:   COMPLEXITY = small   (word limits x 0.60)
   if INPUT_SIZE < 300:   COMPLEXITY = medium  (word limits x 1.00)
   if INPUT_SIZE >= 300:  COMPLEXITY = large   (word limits x 1.20)
   ```
   The `COMPLEXITY` variable determines advisor word limits (see `references/advisors.md`).
   Mies and Stranger are capped at their base limits regardless of complexity scaling.
10. **Cost warning + confirmation:**

```
[Hydra] {{MODE_NAME}} mode -- {{AGENT_COUNT}} agents.
{{PROVIDER_NOTE}}.

Advisors: {{ADVISOR_NAMES}}
Reviewers: {{REVIEWER_COUNT}} ({{REVIEWER_NAMES_OR_NONE}})
Chairman: 1 Opus
{{FOCUS_NOTE_IF_ACTIVE}}

Estimated: {{TIME}}, {{COST}}.

Alternatives:
  --mode quick     -> 4 agents, ~$0.25-0.50, ~1 min
  --no-review      -> broad: 7 agents, ~$1.00, ~1.5 min
  --no-codex       -> secure: 10 agents, ~$1.50, ~2 min
  --no-review --no-codex -> focused: 7 agents, ~$0.75, ~1 min

Proceed? [Y/n/quick]
```

Provider note: Codex modes -> `Code sent to Claude (Anthropic) + Codex (OpenAI). Use --no-codex to keep code Anthropic-only.`
Opus-only modes -> `Code sent to Claude (Anthropic) only.`

### Step 1: Context Enrichment

Quickly scan (< 30 seconds):
- `CLAUDE.md` in project root (use cwd as root if not a git repo)
- Source files the user referenced
- `git diff`, `git log --oneline -5` (skip if not a git repo)
- Project structure (high-level)

**Hard limit: 5000 tokens.** Priority: source code > git diff > CLAUDE.md > project structure.
If `HYDRA_ITERATE`: use `git diff` since previous report timestamp instead of full diff.
Each iteration builds FRESH enriched context. Only Top Actions from the LATEST report
(~100 tokens) are added, not accumulated from all prior reports.
Apply secrets scan to enriched context.

**Context sectioning:** Tag enriched context sections internally for selective routing in Step 3:
- `[SECTION:source_code]` -- file content
- `[SECTION:git_diff]` -- git diff output
- `[SECTION:claude_md]` -- CLAUDE.md contents
- `[SECTION:project_structure]` -- directory tree
- `[SECTION:config_files]` -- package.json, tsconfig, etc.

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
TASK: Re-review -- verify fixes and assess remaining/new issues.
```

### Step 3: Spawn Advisors (parallel)

Read `references/advisors.md`. It defines a Common Preamble (shared by all advisors)
and each advisor's unique prompt. Interpolate `{{FRAMED_QUESTION}}`,
`{{ENRICHED_CONTEXT}}`, and `{{BOUNDARY}}` (use `HYDRA_BOUNDARY_A` from Step 0) into the Common
Preamble, then append each advisor's unique section.

**Selective context routing:** Each advisor receives only the context sections relevant to their scope:
| Advisor | source_code | git_diff | claude_md | project_structure | config_files |
|---------|:-----------:|:--------:|:---------:|:-----------------:|:------------:|
| Cassandra | Y | Y | | | |
| Mies | Y | Y | Y | Y | Y |
| Navigator | Y | Y | | Y | |
| Stranger | Y | Y | | | |
| Volta | Y | Y | | | Y |
| Sentinel | Y | Y | | | |

**Which advisors** -- see Modes table above. In private/stealth mode, Stranger and Sentinel
run as Opus agents (same prompts, spawn via Agent tool instead of Codex). All 6
perspectives are preserved; only cross-model diversity is lost.

**Opus Advisors:** Spawn via Agent tool with `model: "opus"`.

**Codex Advisors** (full and lean modes only -- skip if `CODEX_CIRCUIT_OPEN`).

**IMPORTANT: Codex tasks run SEQUENTIALLY** (codex-companion allows only one active task
per workspace). Launch the first Codex task in the SAME batch as the 4 Opus Agent calls:

```
Batch 1 (dispatch all simultaneously):
  - Agent tool: Cassandra (Opus)
  - Agent tool: Mies (Opus)
  - Agent tool: Navigator (Opus)
  - Agent tool: Volta (Opus)
  - Bash tool: Codex Stranger (see below)

After Stranger Bash returns:
  - Bash tool: Codex Sentinel (see below)
```

**Codex invocation per advisor** (each is a separate Bash tool call):

First, create temp dir (separate Bash call):
```bash
HYDRA_TMP=$(mktemp -d "${TMPDIR:-/tmp}/hydra-XXXXXX") && chmod 700 "$HYDRA_TMP" && echo "$HYDRA_TMP"
```

Write prompt files via Write tool to `$HYDRA_TMP/prompt-stranger.md` and `$HYDRA_TMP/prompt-sentinel.md`.

Then for each Codex advisor (one Bash call per advisor, set Bash tool timeout to 120000ms):

```bash
HYDRA_TMP="{{HYDRA_TMP_PATH}}"
CODEX="{{CODEX_SCRIPT_PATH}}"

# Timeout: gtimeout (brew coreutils) > timeout (linux) > perl fallback
if command -v gtimeout >/dev/null 2>&1; then
  TIMEOUT_CMD="gtimeout 90"
elif command -v timeout >/dev/null 2>&1; then
  TIMEOUT_CMD="timeout 90"
else
  TIMEOUT_CMD="perl -e 'alarm(90); exec @ARGV' --"
fi

$TIMEOUT_CMD node "$CODEX" task \
  --prompt-file "$HYDRA_TMP/prompt-{{ADVISOR_NAME}}.md" \
  --effort {{EFFORT_LEVEL}} \
  > "$HYDRA_TMP/output-{{ADVISOR_NAME}}.txt" 2>"$HYDRA_TMP/stderr-{{ADVISOR_NAME}}.txt"
EXIT_CODE=$?

if [ $EXIT_CODE -eq 124 ]; then
  echo "HYDRA_STATUS=TIMEOUT"
elif [ $EXIT_CODE -ne 0 ]; then
  echo "HYDRA_STATUS=ERROR_$EXIT_CODE"
  echo "STDERR:"
  cat "$HYDRA_TMP/stderr-{{ADVISOR_NAME}}.txt"
else
  echo "HYDRA_STATUS=OK"
  cat "$HYDRA_TMP/output-{{ADVISOR_NAME}}.txt"
fi
```

**Effort strategy:**
| Role | Model | Effort | Rationale |
|------|-------|--------|-----------|
| Stranger | GPT-5.4 | `medium` | Readability = pattern matching, not deep reasoning |
| Sentinel | GPT-5.4 | `high` | Security = thorough analysis of attack surfaces |

**Auth error detection:** After each Codex call, check stderr for auth errors:
```bash
if grep -qi "401\|403\|not authenticated\|unauthorized\|login\|ENOENT" "$HYDRA_TMP/stderr-{{NAME}}.txt" 2>/dev/null; then
  echo "HYDRA_AUTH_FAIL=true"
fi
```
If auth error detected: increment `CODEX_FAILURES`, skip next Codex call immediately.
If timeout (exit 124): increment `CODEX_FAILURES` but still attempt next Codex call (transient).
If other error: increment `CODEX_FAILURES`, attempt next Codex call.

All advisors dispatched in parallel (Opus) and sequentially (Codex, but overlapping with Opus).
Print: `[Hydra] Advisors spawned ({{N}}). Waiting...`
As each completes: `[Hydra] {{Name}} done ({{M}}/{{N}}) {{TIME}}s {{MODEL_TAG}}`

After each advisor completes, validate the response:
- **Valid:** Contains a `POSITION: APPROVE|CONCERN|REJECT` line AND either (1) at least one
  advisor-specific finding field, or (2) an explicit "no findings"/"no issues" statement.
- **Degraded:** Has POSITION line but missing structural fields. Forward with warning:
  `[DEGRADED: missing {{fields}}]`.
- **Invalid:** Missing POSITION line entirely, or response under 100 characters. Mark as
  `[INVALID -- missing POSITION]`. Do not forward to reviewers.
- **Timeout:** Empty or no response within timeout.

**Scan:** Run secrets-scan (Step 0.4) on each advisor output. Silent redact.

**Codex cascade check:** After all advisors complete:
- If both Codex advisors failed/invalid: auto-switch to Opus-only for reviewer phase.
  Print: `[Hydra] Both Codex advisors failed. Reviewers run Opus-only.`
- If only one failed: proceed normally, count toward minimum.
- Auth/script-not-found errors trigger immediate circuit breaker regardless of count.

**Post-cascade model resolution:** Set model labels based on ACTUAL execution:
- If Stranger ran on Opus (cascade or --no-codex): `{{STRANGER_MODEL}}` = "Opus"
- If Sentinel ran on Opus: `{{SENTINEL_MODEL}}` = "Opus"
- If BOTH ran on Opus: remove cross-model rules from chairman prompt.

### Step 4: Peer Review (parallel)

**Skip entirely** if mode has no review phase (lean, stealth, lite).

Read `references/review-protocol.md` for the full protocol.

1. Collect all advisor responses. Label and wrap per `references/review-protocol.md`.
   Use `HYDRA_BOUNDARY_R` (reviewer-stage token) for response delimiters.
2. Spawn 3 Opus reviewers in parallel via Agent tool with `model: "opus"`.

Print: `[Hydra] Peer review started (3 reviewers)...`
As each reviewer completes: `[Hydra] Reviewer {{N}} done ({{M}}/3)`
**Timeout: 120 seconds per reviewer.**

**Scan:** Run secrets-scan on each reviewer output. Silent redact.

### Step 5: Chairman Synthesis

Read `references/chairman-protocol.md` for the protocol and verdict formats.

Spawn 1 Opus agent. Adapt the chairman prompt per the MODE ADAPTATION rules in `references/chairman-protocol.md`.
Use `HYDRA_BOUNDARY_C` (chairman-stage token) for advisor/reviewer delimiters in chairman prompt.

**Chairman input optimization:** Send only the `[SECTION:source_code]` portion of the
enriched context to the chairman (not CLAUDE.md, project structure, or config). The chairman
needs source code for SELF-VERIFY DISPUTES (checking code facts when advisors disagree),
but does not need project metadata. This reduces chairman input by ~50% while preserving
dispute resolution capability.

**Advisor output compression for chairman:** For each advisor output, extract and send:
- The POSITION line
- All severity-labeled findings with their IDs and titles
- All `[VERIFIED]/[HYPOTHESIS]` labels
- File/line references
- First sentence of each finding's lead field
The full advisor outputs remain in the report (Step 6). Chairman receives compressed
versions (~600 tokens each instead of ~2000) for faster, more focused synthesis.

If `HYDRA_ITERATE`: append to the chairman prompt before RULES:

```
ITERATION MODE -- This is a follow-up review. Previous Top Actions:
{{TOP_ACTIONS_FROM_PREV_REPORT}}
After the verdict, produce a DELTA BLOCK (outside word limit, max 200 words):
**Fixed:** [previous actions now resolved, with evidence]
**Remaining:** [previous actions still present -- why?]
**Regression:** [things that WERE working and now aren't -- highest priority]
**New:** [findings not in previous review]
**Drift:** [if changes go beyond original scope -- flag it]
**Complexity Signal:** [if fix is more complex than issue warranted -- flag it]
**Progress:** [X of Y previous actions addressed]
```

**Scan:** Run secrets-scan on chairman output. Silent redact.

### Step 6: Generate Report

Read `references/report-template.md` for the template. Generate inline (no extra agent).

**Final scan:** Run secrets-scan on assembled report before disk write. If findings: redact and append note. If --transcript: scan transcript file too.

**Save to:** `.hydra/reports/hydra-YYYYMMDDTHHMMSS-{slug}.md`
Slug: generate from the first 3-4 words of the title by string manipulation in your
response (do NOT pipe user-derived text into Bash -- shell injection risk):
- Lowercase, replace non-alphanumeric with `-`, collapse consecutive `-`, max 40 chars.
- Example: "Auth Middleware Refactor" -> `auth-middleware-refactor`
If slug is empty after sanitization, use `review`.

**Directory setup (first run):**
```bash
mkdir -p .hydra/reports && chmod 700 .hydra && chmod 700 .hydra/reports
echo '*' > .hydra/.gitignore && chmod 600 .hydra/.gitignore
```

**File permissions:** All files in `.hydra/` should be owner-only:
```bash
chmod 600 .hydra/reports/hydra-*.md
chmod 600 .hydra/state.json
```

   **Write state file:** After saving the report, write `.hydra/state.json`:
   ```json
   {
     "version": 2,
     "latest": {
       "report_path": ".hydra/reports/hydra-{TIMESTAMP}-{SLUG}.md",
       "timestamp_unix": {UNIX_EPOCH},
       "top_actions": [
         {"id": "A1", "severity": "CRITICAL", "file": "path", "lines": "47-62", "effort": "S", "summary": "action text"}
       ],
       "verdict_lead": "first 2-3 sentences of verdict",
       "mode": "{PRESET_NAME}",
       "reviewed_files": ["path/to/file1", ...]
     }
   }
   ```
   Extract `top_actions` from chairman's SUMMARY BLOCK (including effort tags and file refs).
   Extract `reviewed_files` from file paths mentioned in advisor responses.
   If state.json write fails: warn, continue (the report is the primary artifact).

   **Reviewer Highlights:** Extract labeled findings from reviewers:
   - Collect all [CORROBORATED] labels -> **High-Confidence Findings**
   - Collect all [CONTRADICTED] labels -> **Disputes** (chairman must resolve)
   - Collect all [UNCORROBORATED] labels -> **Needs Verification** (single-advisor findings)
   - Collect [CRITICAL MISS] labels -> **Missed by Advisors**
   - Collect [SHARED BLIND SPOT] labels -> **Shared Assumptions**
   - Collect "gap" from each reviewer's Section B -> **Blind Spots**
   If no reviewers ran, omit the Reviewer Highlights and Blind Spots sections entirely.

   **Write audit log:** Append one JSONL line to `.hydra/audit.log`:
   ```json
   {"timestamp":"{{ISO_TIMESTAMP}}","session_id":"HYDRA-{{BASE}}","mode":"{{MODE}}","question_type":"{{TYPE}}","reviewed_files":[...],"advisors":[{"name":"Cassandra","model":"opus","status":"responded","position":"CONCERN"}],"reviewers":[{"number":1,"model":"opus","status":"responded"}],"chairman":{"model":"opus","status":"responded"},"verdict_position":"CONCERN","degradations":[],"report_path":"{{PATH}}","duration_seconds":{{N}},"iteration":false}
   ```
   Create `.hydra/audit.log` with `chmod 600` on first run. Append-only.

   **Report integrity:** After assembling report, compute checksum:
   ```bash
   CHECKSUM=$(shasum -a 256 "$REPORT_PATH" | cut -d' ' -f1)
   ```
   Prepend integrity line to report: `<!-- hydra-integrity: sha256:{{CHECKSUM}} session:HYDRA-{{BASE}} -->`

Omit sections for advisors/reviewers that didn't participate in this mode (don't list
them as timeout). For actual timeouts: mark as `[TIMEOUT -- no response]`.
Omit `## Peer Reviews` if no reviewers ran. Omit `### Cross-Model Signals` if Opus-only.
If fewer than expected responded, add degradation note at top of Verdict section.

If `--transcript`: save raw agent outputs to separate file (see report-template.md).

### Step 7: Present Results

Present in-conversation summary (max 25 lines) using the chairman's SUMMARY BLOCK,
formatted per `references/report-template.md` v2 format.

If `HYDRA_ITERATE`, use the chairman's DELTA BLOCK instead (see report-template.md iteration format).

**Post-review actions:** After presenting the verdict, append:
```
--- Next Steps ---
  fix #N  -> implement Top Action N directly
  hydra iterate -> re-review after fixes
  hydra history -> past reviews
---
```

**`fix #N` trigger:** When user types `fix #1`, read Top Action #1 from `.hydra/state.json`
and implement the fix directly as a normal Claude Code task. Do NOT spawn Hydra agents.

**Cleanup:** Remove temp directory:
```bash
rm -rf "$HYDRA_TMP" 2>/dev/null
```

---

## Error Handling

| Failure | Action |
|---------|--------|
| 0 advisors respond | `[Hydra] ABORTED: 0/N advisors responded. Likely API/network issue. Try again.` |
| Below min advisors | `[Hydra] ABORTED: Only N/M responded (list names). Try: --no-codex or --mode quick` |
| Below min reviewers | Proceed with degraded confidence note in verdict and report. |
| Chairman fails | Generate report without verdict -- include Consensus Map + raw advisor outputs. |
| Codex script not found | Auto-switch to `--no-codex`. Note in report. |
| Codex task fails | Skip advisor, increment CODEX_FAILURES. Check stderr for diagnostics. |
| Codex auth error (401/403) | Immediate circuit breaker. Switch all remaining to Opus. |
| Report write fails | Dump full report inline in conversation as fallback. |
| Secrets in context | Auto-redact, show locations, ask user before proceeding. |
| Both Codex advisors fail | Auto-switch to Opus-only for reviewers. |
| Malformed advisor response | DEGRADED if has POSITION, INVALID if not. See Step 3 validation. |
| Concurrent Hydra run | Warn if recent temp dirs exist (< 5 min). Don't block. |

**Retry logic:** Max 1 retry per advisor/reviewer (5s backoff). Retryable: timeout, 429, 500/502/503.
Non-retryable: 401/403, 400, content policy, script-not-found. On retry:
`[Hydra] {{Name}} failed, retrying (1/1)...`

---

## History Command

Trigger: `hydra history`. No agents spawned, no cost.

```bash
ls -1t .hydra/reports/hydra-*.md 2>/dev/null | grep -v transcript | head -20
```

Present as table: `| # | Date | Title | Report Path |`
Extract date from filename (`hydra-YYYYMMDDTHHMMSS-slug.md`), title from first H1.
If no reports: `[Hydra] No reviews found. Run 'hydra this' to start.`

---

## Auto-Mode (`hydra ?` / `hydra auto`)

When triggered, analyze the question and code before recommending a mode:

```
[Hydra] Analyzing question... (no agents spawned yet)

Question type:    {{CLASSIFICATION}}
Code size:        ~{{LINES}} lines across {{FILES}} files
Risk signals:     {{DETECTED_SIGNALS}}

Recommendation:   {{MODE}} ({{REASON}})

Alternatives:
  {{OTHER_MODES_WITH_COSTS}}

Proceed with {{MODE}}? [Y/n/quick/deep]
```

Signal taxonomy for auto-selection:
- Security keywords (auth, JWT, token, password, crypto, SQL) -> deep or secure
- Code size > 300 lines -> deep or broad
- Code size < 100 lines + no security signals -> quick
- HYDRA_ITERATE + diff < 30 lines -> quick
- Architecture decision (no code, "should I", "vs", "tradeoff") -> broad
- Migration/schema files -> deep
- Test files only -> quick

---

## Branch Review (`hydra branch`)

Trigger: `hydra branch`. Reviews all changes on current branch vs base.

1. Detect base: `git merge-base HEAD main` (fallback: `master`, `develop`)
2. Get diff: `git diff $(git merge-base HEAD main)...HEAD`
3. Get log: `git log --oneline $(git merge-base HEAD main)..HEAD`
4. Auto-classify from branch name: `feat/*` -> feature, `fix/*` -> hotfix, `refactor/*` -> refactor
5. Run standard Hydra with diff as input. Default: quick for <200 lines, lean for 200-500, full for 500+.
