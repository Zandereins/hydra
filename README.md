# Hydra

**Your code review has blind spots. Use more eyes.**

One model misses things. Hydra runs six specialist advisors across Claude Opus and OpenAI
Codex — each asking a fundamentally different question about your code — then
cross-examines their answers and delivers a single verdict with actionable next steps.

> Adapted from [Andrej Karpathy's LLM Council](https://x.com/karpathy) methodology:
> multiple independent AI perspectives, cross-examined and synthesized, produce better
> judgments than any single model call.

---

## Quick Start

```bash
# Install
git clone https://github.com/Zandereins/hydra.git ~/.claude/skills/hydra

# Use (in any Claude Code session)
hydra this: [paste code or describe decision]
```

Hydra asks for cost confirmation before running. Auto-detects Codex; falls back to
Opus-only if unavailable.

**Requirements:** [Claude Code](https://claude.ai/code) (required) |
[Codex CLI plugin](https://github.com/openai/codex-plugin-cc) (optional — enables
cross-model analysis)

---

## Why Not Just Ask Claude?

| | Single model call | Hydra |
|---|---|---|
| Perspectives | 1 | 6 specialized advisors |
| Blind spot detection | None | Cross-model divergence surfaced |
| Security review | Generic | Dedicated adversarial advisor (Sentinel) |
| Performance analysis | If you ask | Always included (Volta) |
| Peer review | None | 5 reviewers challenge advisor claims |
| Structured output | Varies | Consistent verdict with actions |
| Strongest signal | N/A | Independent agreement across Opus + Codex |

**Use Hydra for:** Architecture decisions, security-critical code, refactoring tradeoffs,
"what am I missing?" questions.

**Just ask Claude for:** Syntax fixes, factual lookups, code generation, style questions.

---

## How It Works

```
                         Your Code
                            |
                    [ Context Enrichment ]
                            |
            +-------+-------+-------+-------+-------+
            |       |       |       |       |       |
        Cassandra  Mies  Navigator Stranger Volta  Sentinel
        (Opus)   (Opus)  (Opus)   (Codex) (Opus)  (Codex)
            |       |       |       |       |       |
            +-------+-------+-------+-------+-------+
                            |
                    [ 5 Peer Reviewers ]
                  3 Opus + 2 Codex
                            |
                    [ Chairman (Opus) ]
                            |
                        Verdict
```

---

## The 6 Advisors

| # | Name | Model | Core Question | What They Catch |
|---|------|-------|---------------|-----------------|
| 1 | Cassandra | Opus | "How does this break at 3am?" | Compound failures, unguarded assumptions, missing error paths |
| 2 | Mies | Opus | "What can be deleted?" | Dead code, over-engineering, unnecessary abstractions |
| 3 | Navigator | Opus | "What depends on what?" | Coupling, boundary violations, change propagation |
| 4 | The Stranger | Codex | "Can a stranger understand this in 15 min?" | Misleading names, cognitive overload, lying comments |
| 5 | Volta | Opus | "What does this cost at 10x load?" | N+1 queries, missing indexes, invisible-in-dev costs |
| 6 | Sentinel | Codex | "How do I break this on purpose?" | Auth gaps, injection vectors, race conditions, data loss |

Each advisor has a declared scope boundary — the peer review layer catches what they miss.

---

## Modes

| Mode | Flag | Agents | Time | Est. Cost |
|------|------|--------|------|-----------|
| Full | *(default)* | 12 (6 advisors + 5 reviewers + chairman) | ~2-3 min | ~$3-5 |
| No-Review | `--no-review` | 7 (6 advisors + chairman) | ~1.5 min | ~$2 |
| No-Codex | `--no-codex` | 8 (4 advisors + 3 reviewers + chairman) | ~2 min | ~$3 |
| Lite | `--mode lite` | 4 (Cassandra + Mies + Navigator + chairman) | ~1 min | ~$1 |

Flags combine naturally: `--no-review --no-codex` = 5 agents. `--mode lite` implies both.

---

## Configuration

| Flag | Effect | Default |
|------|--------|---------|
| `--mode lite` | Cassandra + Mies + Navigator + Chairman only | `full` |
| `--no-review` | Skip peer review phase | review ON |
| `--no-codex` | Opus-only, no Codex agents | Codex ON |
| `--transcript` | Save raw agent outputs separately | OFF |

---

## Example Output

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
- Navigator vs Mies on separating auth/authz modules (cross-model:
  Volta sided with Mies). Ruling: keep combined until second consumer exists.

Full report: .hydra/reports/hydra-20260331T144523-auth-middleware-refactor.md
```

---

## How Codex Integration Works

The Stranger and Sentinel run on OpenAI's Codex (GPT-5.4) via the Codex CLI plugin. Two of the
five peer reviewers also run on Codex. This matters because:

- **Different training data** catches different bugs. Opus might miss a performance
  pattern that Codex flags, and vice versa.
- **Cross-model consensus** (both models independently agree) is a stronger signal than
  same-model agreement.
- **Cross-model divergence** (models disagree) is the highest-value signal — the chairman
  surfaces these prominently.

When Codex is unavailable, Hydra runs Opus-only. You still get four advisors, three
reviewers, and a chairman — just without the cross-model dimension.

---

## Cost

Full Hydra runs 12 parallel agents and costs roughly $3-5. Lite mode costs around $1.
Think of it as a 2-minute panel review by six specialists — cheaper than a missed
production incident.

Reports are saved to `.hydra/reports/` (auto-gitignored) for reference.

---

## Prerequisites

- **Claude Code** — required. Hydra runs as a Claude Code skill.
- **Codex CLI plugin** — optional. Enables cross-model analysis (Stranger, Sentinel, and 2
  Codex reviewers). Without it, Hydra auto-falls back to `--no-codex` mode.

---

## Attribution

The multi-agent council approach is adapted from Andrej Karpathy's LLM Council
methodology — the idea that multiple independent AI perspectives, cross-examined and
synthesized, produce better judgments than any single model call.

---

## License

MIT
