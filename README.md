# Hydra

**Your code review has blind spots. Use more eyes.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-D97757)](https://docs.anthropic.com/en/docs/claude-code/skills)
[![Agents](https://img.shields.io/badge/Agents-12_parallel-blue)](#modes)

Six specialists ask six different questions about your code, cross-examine each
other's answers, and deliver one verdict. Inspired by
[Karpathy's LLM Council](https://github.com/karpathy/llm-council) — same principle
(independent perspectives, cross-examination, synthesis), adapted for specialist
code review with cross-model diversity (Claude Opus + OpenAI Codex).

---

## What You Get

```
## Hydra Verdict: auth-middleware-refactor

**Solid refactor with one critical gap in token refresh handling.**

The middleware correctly centralizes auth checks, but the refresh token
flow has a race condition under concurrent requests — Cassandra and
Sentinel (cross-model consensus) both flagged this independently.
Mies identified two abstraction layers that can be collapsed.

**Top Actions:**
1. Add mutex around token refresh in auth/middleware.ts:47-62
2. Remove SessionValidatorFactory — inline the 3-line check (auth/validators.ts)
3. Add integration test for concurrent refresh scenario

**Key Tensions:**
- Navigator vs Mies on separating auth/authz modules (Stranger sided
  with Mies — cross-model). Ruling: keep combined until second consumer exists.

Full report: .hydra/reports/hydra-20260331T144523-auth-middleware-refactor.md
```

**Best for:** Architecture decisions, security-critical code, refactoring tradeoffs,
pre-merge deep reviews.
**Just ask Claude for:** Syntax fixes, factual lookups, code generation, style questions.

---

## How It Works

```mermaid
graph TD
    A[User Code + Question] --> B[Pre-flight + Context Enrichment]
    B --> C[Frame Question]

    C --> D1[Cassandra · Opus]
    C --> D2[Mies · Opus]
    C --> D3[Navigator · Opus]
    C --> D4[Volta · Opus]
    C --> D5[Stranger · Codex]
    C --> D6[Sentinel · Codex]

    subgraph Advisors — parallel, independent
        D1
        D2
        D3
        D4
        D5
        D6
    end

    D1 & D2 & D3 & D4 & D5 & D6 --> E[All Advisor Outputs]

    E --> R1[Reviewer 1 · Opus]
    E --> R2[Reviewer 2 · Opus]
    E --> R3[Reviewer 3 · Opus]
    E --> R4[Reviewer 4 · Codex]
    E --> R5[Reviewer 5 · Codex]

    subgraph Cross-Examination — each reviewer sees ALL outputs
        R1
        R2
        R3
        R4
        R5
    end

    R1 & R2 & R3 & R4 & R5 --> F[Chairman · Opus]
    F --> G[Verdict + Report]
    G -. hydra iterate .-> B
```

Six advisors analyze independently in parallel — four on Opus, two on Codex. Five reviewers then cross-examine all advisor outputs (the key differentiator: no advisor sees another's work, but every reviewer sees everything). The chairman synthesizes a final verdict. After fixes, `hydra iterate` re-enters the pipeline in Lite mode, producing a delta of what changed.

---

## Quick Start

```bash
# Install
git clone https://github.com/Zandereins/hydra.git ~/.claude/skills/hydra

# Review
hydra this: [paste code or describe decision]

# Fix issues, then iterate
hydra iterate
```

Hydra asks for cost confirmation before running. Auto-detects Codex; falls back to
Opus-only if unavailable. Iterations default to Lite mode (~$0.50-1.50) and show a
delta: what's fixed, what remains, what's new.

**Requirements:** [Claude Code](https://claude.ai/code) (required) |
[Codex CLI plugin](https://github.com/openai/codex-plugin-cc) (optional — enables
cross-model analysis)

---

## The 6 Advisors

Each advisor asks a fundamentally different question. Four run on Claude Opus,
two on OpenAI Codex — different model, different blind spots. When Opus and Codex
independently agree, that's the strongest signal. When they disagree, that's the
highest-value finding.

| # | Name | Model | Core Question |
|---|------|-------|---------------|
| 1 | Cassandra | Opus | "How does this break at 3am?" — compound failures, unguarded assumptions |
| 2 | Mies | Opus | "What can be deleted?" — dead code, over-engineering |
| 3 | Navigator | Opus | "What depends on what?" — coupling, boundary violations |
| 4 | The Stranger | Codex | "Can a stranger understand this in 15 min?" — naming, cognitive load |
| 5 | Volta | Opus | "What does this cost at 10x load?" — N+1 queries, invisible costs |
| 6 | Sentinel | Codex | "How do I break this on purpose?" — auth gaps, injection, race conditions |

Advisors run in parallel, then 5 peer reviewers cross-examine their work
(3 Opus + 2 Codex), then a chairman (Opus) synthesizes the final verdict.

---

## Modes

| Mode | CLI | Agents | Est. Cost |
|------|-----|--------|-----------|
| **full** *(default)* | — | 12 (6 advisors + 5 reviewers + chairman) | ~$5-7 |
| **lean** | `--no-review` | 7 (6 advisors + chairman) | ~$2 |
| **private** | `--no-codex` | 10 (all Opus) | ~$3-4 |
| **stealth** | `--no-review --no-codex` | 7 (all Opus, no review) | ~$1-2 |
| **lite** | `--mode lite` | 4 (Cassandra + Sentinel + Stranger + chairman) | ~$0.50-1.50 |

Flags combine: `--no-review --no-codex` = stealth (7 agents). `--mode lite` is its own preset (4 agents) — other flags are ignored.
`--transcript` saves raw agent outputs separately.

Costs are for API calls to Claude and Codex — charged to your own accounts.
Hydra always shows the estimate and asks before running.

---

## Iterate

Hydra reviews aren't one-shot. Fix the issues, then run `hydra iterate` to verify:

```
## Hydra Delta: auth-middleware-refactor

**Progress: 2/3 previous actions addressed**

**Fixed:** Mutex added around token refresh. SessionValidatorFactory removed.
**Remaining:** Integration test for concurrent refresh not yet added.
**New Issues:** None.

**Next Step:** Add test in auth/__tests__/refresh.test.ts
```

Iterations auto-detect the last report, diff only what changed, and default to
Lite mode. Run as many cycles as needed — each one costs ~$0.50-1.50.

Triggers: `hydra iterate`, `hydra re-review`, `hydra follow-up`, `check my fixes`.

---

## Privacy

In full mode, your code is sent to both Anthropic (Claude Opus) and OpenAI
(Codex GPT-5.4). Use `--no-codex` to keep everything Anthropic-only. Hydra shows
which providers receive your code and asks for confirmation before any agents run.

Without the Codex plugin, Hydra runs all 6 advisors on Opus (10 agents). You still
get all perspectives — just without cross-model diversity.

---

## When NOT to Use Hydra

Hydra spawns 4-12 parallel agents. Use it for decisions that benefit from multiple
perspectives — not everything.

**Just ask Claude directly for:** syntax fixes, single-file refactors, code generation,
factual lookups, style questions, simple bug fixes with obvious root causes.

**Use Hydra for:** architecture decisions with real tradeoffs, security-critical code,
complex refactoring, pre-merge reviews, "I've been staring at this for hours" situations,
code where mistakes have high cost (payments, auth, data migration).

**Rule of thumb:** If you can describe the change in one sentence and the approach is
obvious, you don't need Hydra.

---

## Troubleshooting

**"Codex script not found"** — Hydra auto-switches to Opus-only. All 6 perspectives
still run. Install the [Codex CLI plugin](https://github.com/openai/codex-plugin-cc)
for cross-model analysis.

**Advisors timing out** — Default timeout is 120s. Common causes: API rate limits,
large input (keep under 500 lines), network issues. Try `--mode lite` if persistent.

**"ABORTED: 0/N advisors responded"** — API key or network issue. Verify Claude access
works outside Hydra.

**Unexpected activation** — Type `n` at the cost confirmation. Hydra always asks before
spawning agents.

---

## FAQ

**How much does it cost?** Full: ~$5-7. Lite: ~$0.50-1.50. These are API costs charged
to your accounts. Hydra shows estimates before running.

**Where are reports?** `.hydra/reports/` in your project root (gitignored). Run
`hydra history` to list past reviews.

**Without Codex?** All 6 advisors run on Opus (10 agents total with reviewers).
Same perspectives, no cross-model signal. Use `--no-codex` to keep code Anthropic-only.

**How do iterations work?** Fix issues, run `hydra iterate`. Hydra diffs what changed,
defaults to Lite (~$0.50-1.50), shows a delta: fixed / remaining / new.

---

## License

MIT
