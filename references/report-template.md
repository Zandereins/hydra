# Hydra Report Template

Save to `.hydra/reports/hydra-YYYYMMDDTHHMMSS-{slug}.md`.
Slug = first 3-4 words, kebab-case, `[a-z0-9-]` only, max 40 chars. Fallback: `review`.
`{{TITLE}}` = one-line summary of the reviewed subject, derived from user's input.
Create `.hydra/.gitignore` with `*` on first run.

**Status labels:**
- `responded` — advisor/reviewer completed successfully
- `timeout` — spawned but did not respond within 120s
- `not run` — excluded by active mode (e.g., Mies/Navigator/Volta in `--mode lite`)

**Mode-aware sections:**
- Keep status table rows for excluded roles as `not run`. Omit their full response sections.
- Omit `## Peer Reviews` entirely if `--no-review` or `--mode lite`.
- Omit `### Cross-Model Signals` if running Opus-only (`--no-codex` or `--mode lite`).
- In `--no-codex` mode or `--mode lite`: replace "Codex" with "Opus" in Model column and section headings.
- Thresholds and mode definitions: see SKILL.md Modes table (single source of truth).
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
{{CHAIRMAN_CONSENSUS_MAP}}
<!-- Orchestrator: extract the Consensus Map table from the chairman's output
     (produced per CONSENSUS MAP rule). The chairman owns position overrides and findings. -->

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

{{VERDICT_LEAD}}
<!-- Orchestrator: extract 2-3 sentences from chairman verdict lead —
     Summary (code review), Recommendation (arch), Risk Level (security), or Answer (debug). -->

**Top Actions:**
1. {{action with file/function reference}}
2. {{action}}
3. {{action}}

**Key Tensions:**
- {{disagreement — note if cross-model}}

Full report: `.hydra/reports/hydra-{{TIMESTAMP}}-{{SLUG}}.md`
```

---

## In-Conversation Summary — Iteration Mode (if `HYDRA_ITERATE`)

Use the chairman's DELTA BLOCK instead of the standard summary:

```
## Hydra Delta: {{TITLE}}

**Progress: {{X}}/{{Y}} previous actions addressed**

**Fixed:** {{resolved actions from previous Top Actions}}
**Remaining:** {{unresolved actions}}
**New Issues:** {{findings not in previous review, if any}}

**Next Step:** {{ONE action}}

Full report: `.hydra/reports/hydra-{{TIMESTAMP}}-{{SLUG}}.md`
Previous: `{{PREV_REPORT}}`
```

---

## Transcript (if `--transcript`)

Save raw outputs to `.hydra/reports/hydra-YYYYMMDDTHHMMSS-{slug}-transcript.md`.
Dump each section under its heading. Include advisor label mappings (A=Cassandra, etc.).
