# ADR 0002 — Relationship between Hydra and the general-purpose LLM-Council method

- **Status:** Accepted, 2026-05-26
- **Date:** 2026-05-26
- **Deciders:** Franz
- **Supersedes:** —
- **Context source:** Evaluation of Karpathy's "LLM Council" skill against Hydra's
  actual prompt internals (`references/advisors.md`, `references/review-protocol.md`,
  `references/chairman-protocol.md`), 2026-05-26.

## Context

The question was raised: should the general-purpose **LLM-Council** method (Karpathy:
5 advisors with general thinking lenses → anonymized peer review → chairman synthesis,
for *any* high-stakes decision) be "built into" Hydra?

A grounded comparison against the live Hydra prompts shows that **Hydra is already a
rigorous superset of the LLM-Council pattern, specialized for code review** — not a
tool that lacks it:

| LLM-Council (general) | Hydra (verified in `references/`) |
|---|---|
| 5 advisors, independent, distinct lenses | 4–6 advisors, **multi-model** (Opus + Codex), distinct code-review lenses |
| Anonymized peer review (A–E) | 3 peer reviewers (Cross-Examiner / Effort-Risk Ranker / Devil's Advocate) over labeled responses |
| Chairman synthesis | Chairman + verdict (APPROVE / CONCERN / REJECT) |
| agree / clash / blind-spots / recommendation / first-step | Consensus Map, Cross-Model Signals, Disputed Points, `[SHARED BLIND SPOT]`, Effort-Risk ranked list |
| — | **grounding** (chairman re-verifies code facts), **cross-model confidence**, severity/CWE, determinism, a **measurable benchmark** |

The "Outsider / fresh-eyes" lens already exists as **Mies+ Advisor 2** ("zero-context
first-reader"). The "Expansionist / upside" lens is deliberately absent — code review
is about risk, not opportunity.

### The genuine deltas LLM-Council has that Hydra does not

1. **Randomized response anonymization** in the peer-review round. Hydra uses *stable,
   known* A–F labels by deliberate choice (`review-protocol.md` — "no permutation
   needed"); the bias surface is smaller because reviewers judge on cited code
   evidence, but per-reviewer permutation is a cheap, **bench-testable** bias
   experiment — traded off against chairman traceability.
2. **A First-Principles lens** ("is this PR solving the right problem / is the approach
   right?"). Echo (scope-creep) and Cassandra (architecture) touch it; **none owns it.**
3. **Domain generality.** LLM-Council answers *non-code* decisions (strategy,
   positioning, "X or Y"). Hydra is code-locked by design (ADR 0001 + the entire bench).

## Decision

1. **Do not rebuild or dilute Hydra into a general decision tool.** Hydra remains the
   code & code-architecture review council; it already surpasses the generic pattern
   for that domain.
2. **Keep `llm-council` as a separate, general-purpose decision tool.** Boundary:
   - **Code / PR / diff / codebase / architecture review → Hydra.**
   - **General high-stakes decisions (strategy, business, positioning, "X or Y") → llm-council.**
   Disambiguate the overlapping triggers (Hydra advertises "tradeoff analysis", "what
   am I missing", "architecture decisions"; the council advertises "pressure-test this",
   "should I X or Y") by this code-vs-general boundary.
3. **Harvest only the small, code-relevant delta — later.** A First-Principles
   "right-problem / right-approach" check (and optionally an A/B of randomized
   peer-review anonymization, measured on the bench) is worth adding to interactive
   `/hydra`. This is an **interactive-prompt change (harness side per ADR 0001), a
   separate track from Track-3 (the bench)** and is **deferred until after Track-3
   ships**, so the calibrated-benchmark milestone is not derailed mid-flight.

## Consequences

- **Positive:** both tools stay sharp; no identity dilution; no new untrusted-input
  surface; Track-3 stays focused; the one genuine improvement (First-Principles check)
  is small and measurable on the very benchmark being calibrated.
- **Negative / deferred:** the First-Principles lens and the anonymization experiment
  are not delivered now; trigger-overlap between Hydra and the council relies on the
  documented code-vs-general boundary rather than hard enforcement.
- **Follow-up (post-Track-3):** scope a small interactive-`/hydra` prompt track for the
  First-Principles check + anonymization A/B, with the same audit-to-convergence
  discipline used for Track-1/Track-2.
