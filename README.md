# Hydra

**Your code review has blind spots. Use more eyes.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-D97757)](https://docs.anthropic.com/en/docs/claude-code/skills)
[![Codex Compatible](https://img.shields.io/badge/Codex-Compatible-10a37f)](https://github.com/openai/codex-plugin-cc)
[![Agents](https://img.shields.io/badge/Agents-12_parallel-blue)](#modes)

One model misses things. Hydra runs six specialist advisors across Claude Opus and OpenAI
Codex — each asking a fundamentally different question about your code — then
cross-examines their answers and delivers a single verdict with actionable next steps.

Built on [Andrej Karpathy's LLM Council](https://x.com/karpathy) methodology.

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

Plus a full report saved to `.hydra/reports/` with all advisor responses, peer reviews,
consensus map, and cross-model signals.

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

### The 6 Advisors

| # | Name | Model | Core Question | What They Catch |
|---|------|-------|---------------|-----------------|
| 1 | Cassandra | Opus | "How does this break at 3am?" | Compound failures, unguarded assumptions, missing error paths |
| 2 | Mies | Opus | "What can be deleted?" | Dead code, over-engineering, unnecessary abstractions |
| 3 | Navigator | Opus | "What depends on what?" | Coupling, boundary violations, change propagation |
| 4 | The Stranger | Codex | "Can a stranger understand this in 15 min?" | Misleading names, cognitive overload, lying comments |
| 5 | Volta | Opus | "What does this cost at 10x load?" | N+1 queries, missing indexes, invisible-in-dev costs |
| 6 | Sentinel | Codex | "How do I break this on purpose?" | Auth gaps, injection vectors, race conditions, data loss |

Cross-model advisors (Stranger on Codex, Sentinel on Codex) catch blind spots that
same-model analysis misses. When Opus and Codex independently agree, that's the
strongest signal. When they disagree, that's the highest-value finding.

---

## Modes

| Mode | Flag | Agents | Time | Est. Cost |
|------|------|--------|------|-----------|
| Full | *(default)* | 12 (6 advisors + 5 reviewers + chairman) | ~2-3 min | ~$3-5 |
| No-Review | `--no-review` | 7 (6 advisors + chairman) | ~1.5 min | ~$2 |
| No-Codex | `--no-codex` | 10 (Opus only) | ~2 min | ~$4 |
| Lite | `--mode lite` | 4 (Cassandra + Mies + Navigator + chairman) | ~1 min | ~$1 |

Flags combine naturally: `--no-review --no-codex` = 7 agents. `--mode lite` implies both.

Additional flags: `--transcript` saves raw agent outputs separately.

Think of it as a 2-minute panel review by six specialists — cheaper than a missed
production incident.

---

## FAQ

<details>
<summary><strong>Is my code sent to OpenAI?</strong></summary>

In full mode, your code is sent to both Anthropic (Claude Opus) and OpenAI (Codex GPT-5.4).
Use `--no-codex` to keep code Anthropic-only. Hydra shows which providers receive your
code in the cost confirmation before any agents run.
</details>

<details>
<summary><strong>Why not just ask Claude to review my code?</strong></summary>

A single model call gives you one perspective. Hydra gives you six specialists that each
ask a fundamentally different question, five reviewers that challenge their claims, and a
chairman that synthesizes a verdict. Cross-model analysis (Opus + Codex) catches blind
spots that same-model repetition misses.

Best for: Architecture decisions, security-critical code, refactoring tradeoffs.
Just ask Claude for: Syntax fixes, factual lookups, code generation, style questions.
</details>

<details>
<summary><strong>Do I need the Codex plugin?</strong></summary>

No. Codex is optional. Without it, Hydra runs all 6 advisors on Opus (6 advisors +
3 reviewers + chairman = 10 agents). You still get all perspectives — just without
the cross-model dimension.
</details>

<details>
<summary><strong>How much does it cost?</strong></summary>

Full mode: ~$3-5 per review (12 agents). Lite mode: ~$1 (4 agents). These costs are for
the API calls to Claude and Codex — charged to your own API accounts. Hydra always shows
the cost estimate and asks for confirmation before running.
</details>

---

## Attribution

Built on [Andrej Karpathy's LLM Council](https://x.com/karpathy) methodology — multiple
independent AI perspectives, cross-examined and synthesized, produce better judgments than
any single model call.

## License

MIT
