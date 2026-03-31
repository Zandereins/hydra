# Hydra Report Template

Save to `.hydra/reports/hydra-YYYYMMDDTHHMM-{slug}.md`. Slug = first 3-4 words, kebab-case.
Create `.hydra/.gitignore` with `*` on first run.

For timed-out advisors/reviewers: mark as `[TIMEOUT — no response]`.

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
| The Stranger | Opus | {{responded/timeout}} |
| Volta | Codex | {{responded/timeout}} |
| Sentinel | Codex | {{responded/timeout}} |

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
| The Stranger (Opus) | {{pos}} | {{finding}} |
| Volta (Codex) | {{pos}} | {{finding}} |
| Sentinel (Codex) | {{pos}} | {{finding}} |

Position values: APPROVE | CONCERN | REJECT | N/A (timeout)
Orchestrator classification: REJECT = any CATASTROPHIC/CRITICAL finding. CONCERN = SERIOUS/HIGH.
APPROVE = only MODERATE/LOW or no findings. N/A = timeout.

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

### The Stranger — Adversarial First-Reader (Opus)
{{FULL_RESPONSE or [TIMEOUT]}}

### Volta — Efficiency Surgeon (Codex)
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
- CODE_REVIEW → first sentence of chairman Summary
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

Save raw outputs to `.hydra/reports/hydra-YYYYMMDDTHHMM-{slug}-transcript.md`.
Dump each section under its heading. Include anonymization mappings.
