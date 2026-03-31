# Hydra

**Multi-headed cross-model code review for Claude Code.**

Six independent advisors -- four on Claude Opus, two on OpenAI Codex -- analyze your code from fundamentally different angles. Five reviewers cross-examine their work. A chairman synthesizes a final verdict. Different models, different training data, different blind spots.

Adapted from [Andrej Karpathy's LLM Council](https://x.com/karpathy) methodology.

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
        (Opus)   (Opus)  (Opus)   (Opus)  (Codex) (Codex)
            |       |       |       |       |       |
            +-------+-------+-------+-------+-------+
                            |
                    [ 5 Peer Reviewers ]
                3 Opus + 2 Codex, anonymous
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
| 4 | The Stranger | Opus | "Can a stranger understand this in 15 min?" | Misleading names, cognitive overload, lying comments |
| 5 | Volta | Codex | "What does this cost at 10x load?" | N+1 queries, missing indexes, invisible-in-dev costs |
| 6 | Sentinel | Codex | "How do I break this on purpose?" | Auth gaps, race conditions, prompt injection, data loss |

Each advisor has a declared blind spot. The peer review layer catches what they miss.

---

## Quick Start

1. Copy the `hydra` folder to `~/.claude/skills/hydra/`
2. In any Claude Code session, say: `hydra this: [paste code or describe decision]`
3. Confirm the cost estimate, wait ~2 minutes, get a structured verdict with actionable next steps

Hydra auto-detects whether Codex is installed and adjusts accordingly.

---

## Modes

| Mode | Flag | Agents | Time | Est. Cost |
|------|------|--------|------|-----------|
| Full | *(default)* | 12 (6 advisors + 5 reviewers + chairman) | ~2-3 min | ~$3-5 |
| No-Review | `--no-review` | 7 (6 advisors + chairman) | ~1.5 min | ~$2 |
| No-Codex | `--no-codex` | 8 (4 advisors + 3 reviewers + chairman) | ~2 min | ~$3 |
| Lite | `--mode lite` | 4 (Cassandra + Mies + Navigator + chairman) | ~1 min | ~$1 |

Lite mode skips cross-model analysis but still gives you three expert perspectives and a synthesized verdict.

---

## Prerequisites

- **Claude Code** -- required. Hydra runs as a Claude Code skill.
- **Codex CLI plugin** -- optional. Enables cross-model analysis (Volta, Sentinel, and 2 Codex reviewers). Without it, Hydra auto-falls back to `--no-codex` mode.

---

## Cost

Full Hydra runs 12 parallel agents and costs roughly $3-5. Lite mode costs around $1. Think of it as a 2-minute panel review by six specialists -- cheaper than a missed production incident.

Reports are saved to `.hydra/reports/` (auto-gitignored) for reference.

---

## Example Output

What you see in-conversation after a full run:

```
## Hydra Verdict: auth-middleware-refactor

**Solid refactor with one critical gap in token refresh handling.**

The middleware correctly centralizes auth checks, but the refresh token
flow has a race condition under concurrent requests -- Cassandra and
Sentinel (cross-model consensus) both flagged this independently.
Mies identified two abstraction layers that can be collapsed.

**Top Actions:**
1. Add mutex around token refresh in auth/middleware.ts:47-62
2. Remove SessionValidatorFactory -- inline the 3-line check (auth/validators.ts)
3. Add integration test for concurrent refresh scenario

**Key Tensions:**
- Navigator vs Mies on separating auth/authz modules (cross-model:
  Volta sided with Mies). Ruling: keep combined until second consumer exists.

Full report: .hydra/reports/hydra-20260331T1445-auth-middleware-refactor.md
```

---

## Configuration

| Flag | Effect | Default |
|------|--------|---------|
| `--mode lite` | Cassandra + Mies + Navigator + Chairman only | `full` |
| `--no-review` | Skip peer review phase | review ON |
| `--no-codex` | Opus-only, no Codex agents | Codex ON (if available) |
| `--transcript` | Save raw agent outputs separately | OFF |

---

## How Codex Integration Works

Volta and Sentinel run on OpenAI's Codex (GPT-5.4) via the Codex CLI plugin. Two of the five peer reviewers also run on Codex. This matters because:

- **Different training data** catches different bugs. Opus might miss a performance pattern that Codex flags, and vice versa.
- **Cross-model consensus** (both models independently agree) is a stronger signal than same-model agreement.
- **Cross-model divergence** (models disagree) is the highest-value signal -- the chairman surfaces these prominently.

When Codex is unavailable, Hydra runs Opus-only. You still get four advisors, three reviewers, and a chairman -- just without the cross-model dimension.

---

## Question Types

Hydra classifies your input and adapts the verdict format:

| Type | Verdict Style |
|------|---------------|
| `CODE_REVIEW` | Critical issues, improvements, disputed points |
| `ARCHITECTURE_DECISION` | Recommendation with confidence level and tradeoff table |
| `SECURITY_AUDIT` | Risk level with findings ranked by severity |
| `DEBUGGING` | Root cause with confidence and evidence chain |
| `GENERAL_TECHNICAL` | Direct answer with key considerations |

---

## Attribution

The multi-agent council approach is adapted from Andrej Karpathy's LLM Council methodology -- the idea that multiple independent AI perspectives, cross-examined and synthesized, produce better judgments than any single model call.

---

## License

MIT
