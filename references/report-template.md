# Hydra Report Template

Save to `.hydra/reports/hydra-YYYYMMDDTHHMMSS-{slug}.md`.
Slug = first 3-4 words, kebab-case, `[a-z0-9-]` only, max 40 chars. Fallback: `review`.
`{{TITLE}}` = one-line summary of the reviewed subject, derived from user's input.
Create `.hydra/.gitignore` with `*` on first run.

**Status labels:**
- `responded` — advisor/reviewer completed successfully
- `timeout` — spawned but did not respond within 120s
- `not run` — excluded by active mode (e.g., Volta in `--no-codex`)

**Mode-aware sections:**
- Omit advisor rows/sections for roles that didn't run (don't mark as timeout).
- Omit `## Peer Reviews` entirely if `--no-review` or `--mode lite`.
- Omit `### Cross-Model Signals` if running Opus-only (`--no-codex` or `--mode lite`).
- If fewer than expected responded, add after the Verdict heading:
  `> **Note:** Degraded confidence — only {{N}} of {{M}} responded.`

---

## Report

```markdown
# Hydra Report: {{TITLE}}

> {{TIMESTAMP}} | {{QUESTION_TYPE}}

| Role | Model | Status |
|------|-------|--------|
| Cassandra | Opus | {{responded/timeout}} |
| Mies | Opus | {{responded/timeout}} |
| Navigator | Opus | {{responded/timeout}} |
| The Stranger | Codex | {{responded/timeout/not run}} |
| Volta | Opus | {{responded/timeout}} |
| Sentinel | Codex | {{responded/timeout/not run}} |

---

## Verdict

{{CHAIRMAN_VERDICT}}

---

## Consensus Map

| Advisor (Model) | Position | Key Finding |
|-----------------|----------|-------------|
| Cassandra (Opus) | {{APPROVE/CONCERN/REJECT}} | {{finding, max 60 chars}} |
| Mies (Opus) | {{pos}} | {{finding}} |
| Navigator (Opus) | {{pos}} | {{finding}} |
| The Stranger (Codex) | {{pos}} | {{finding}} |
| Volta (Opus) | {{pos}} | {{finding}} |
| Sentinel (Codex) | {{pos}} | {{finding}} |

Position values: APPROVE | CONCERN | REJECT | N/A (timeout/not run)
Orchestrator classification:
- REJECT = any CATASTROPHIC finding (Cassandra, Volta) or HIGH-confidence verified vulnerability (Sentinel)
- CONCERN = SERIOUS finding, or advisor recommends significant changes (Mies: remove abstraction touching 3+ callers, Navigator: restructuring 3+ dependency layers, Stranger: cognitive load requiring 5+ working memory items)
- APPROVE = only MODERATE/LOW findings, or no findings
- N/A = timeout or not participating in this mode

### Cross-Model Signals

{{Where Opus and Codex diverged or converged — highest-value insights}}

---

## Reviewer Highlights

{{Synthesized: strongest/weakest advisor, shared blind spots, devil's advocate counter-case}}

---

## The Question

{{FRAMED_QUESTION}}

---

## Full Advisor Responses

### Cassandra — Failure Archaeologist (Opus)
{{FULL_RESPONSE or [TIMEOUT]}}

### Mies — Reductionist (Opus)
{{FULL_RESPONSE or [TIMEOUT]}}

### Navigator — Systems Cartographer (Opus)
{{FULL_RESPONSE or [TIMEOUT]}}

### The Stranger — Adversarial First-Reader (Codex)
{{FULL_RESPONSE or [TIMEOUT]}}

### Volta — Efficiency Surgeon (Opus)
{{FULL_RESPONSE or [TIMEOUT]}}

### Sentinel — Adversarial Security (Codex)
{{FULL_RESPONSE or [TIMEOUT]}}

---

## Peer Reviews

### Reviewer 1 — Technical Correctness (Opus)
{{FULL_REVIEW or [TIMEOUT]}}

### Reviewer 2 — Implementation Critic (Opus)
{{FULL_REVIEW or [TIMEOUT]}}

### Reviewer 3 — Scope & Risk (Opus)
{{FULL_REVIEW or [TIMEOUT]}}

### Reviewer 4 — Assumption Excavator (Codex)
{{FULL_REVIEW or [TIMEOUT]}}

### Reviewer 5 — Devil's Advocate (Codex)
{{FULL_REVIEW or [TIMEOUT]}}

---

*Hydra v1.0 | Based on Karpathy's LLM Council methodology | MIT License*
```

---

## In-Conversation Summary (max 25 lines)

Map question type to signal line:
- CODE_REVIEW → `**{{one-sentence quality assessment from chairman}}**`
- ARCHITECTURE_DECISION / DEBUGGING / GENERAL_TECHNICAL → **Confidence: {{level}}**
- SECURITY_AUDIT → **Risk Level: {{level}}**

```
## Hydra Verdict: {{TITLE}}

**{{SIGNAL_LINE}}**

{{CHAIRMAN_SUMMARY — 2-3 sentences}}

**Top Actions:**
1. {{action with file/function reference}}
2. {{action}}
3. {{action}}

**Key Tensions:**
- {{disagreement — note if cross-model}}

Full report: `.hydra/reports/hydra-{{TIMESTAMP}}-{{SLUG}}.md`
```

---

## Transcript (if `--transcript`)

Save raw outputs to `.hydra/reports/hydra-YYYYMMDDTHHMMSS-{slug}-transcript.md`.
Dump each section under its heading. Include anonymization mappings.
