# Spec — Untraced-Links Ledger + Coverage Gate

**Status:** ready to implement · **Created:** 2026-07-30 · **Baseline:** `main @ 144be2c`
**Trigger:** maintain-mode trigger (i) — a defect surfaced by REAL USE of Hydra on external code.
**All line numbers below were read from the files at `144be2c`. Re-read every anchor before editing.**

---

## 1. Ziel

Make Hydra act on its own "we could not see enough" signal, instead of letting it evaporate
between the advisor phase and the peer-review phase.

Two concrete outcomes:
- **D1** — advisors must report *which* link is untraced, in machine-readable form.
- **D2** — the orchestrator must resolve or explicitly forward those gaps **before** reviewers run.

---

## 2. Kontext — wie der Defekt gefunden wurde

On 2026-07-29 Hydra ran `--mode deep --focus security` against external OSS
(`diegosouzapw/OmniRoute` @ release `v3.8.48`, commit `7ee5bbc`) on a 3-file trust-chain question.
The report was written into a throwaway scratchpad clone that is NOT preserved; everything that
matters is reproduced here.

What happened, measured:

1. The orchestrator scoped **3 files**; the trust chain spans **>=6 modules**.
2. **3 of 6 advisors reported the gap** (Sentinel Se-2, Mies+ M-5, Navigator N-5): "the decisive
   file was not shown". Both Codex advisors volunteered a traced-vs-assumed ledger.
3. **The signal was not actionable.** The orchestrator launched the review phase anyway.
4. Two CATASTROPHIC findings rested entirely on the absence of one unshown file
   (`src/server/authz/policies/management.ts` in the target repo).
5. **Both peer reviewers UPHELD the false CATASTROPHIC** ("SURVIVES" / "could not break it") —
   because they were handed the same incomplete substrate.
6. Only an out-of-band orchestrator measurement, taken *after* the reviewers had launched, refuted
   it. The chairman then corrected the record.

**Durable lesson, confirmed live:** the review layer does not correct orchestrator scope error — it
amplifies it. Adding reviewers would not have helped; all three shared one blind substrate.

### Das rote Signal (reproduzierbar, deterministisch, < 1 s)

```bash
cd ~/.claude/skills/hydra
grep -cE 'traced|assumed' references/advisors.md      # -> 0   RED: ledger is not in the skill
grep -n '^### Step [34]' SKILL.md                     # -> 437, 651   RED: nothing in between
```

The traced-vs-assumed ledger that both Codex advisors produced — and that both reviewers praised —
came from an **ad-hoc sentence the orchestrator typed into the prompt for that single run**. It is
not in `references/advisors.md`. Without that ad-hoc text the next run loses the property entirely.

`SKILL.md:679` ("Coverage gaps") is a DIFFERENT mechanism: it collects *findings missing a file
path*, and it runs in Step 5 — after the reviewers. It does not cover this case.

### Gegenprobe — hätte der Fix DIESEN Lauf gerettet?

Yes, and that counterfactual is the entire justification. With D1 in place, Se-2 / M-5 / N-5 would
each have emitted `untraced_links` naming `src/shared/constants/spawnCapablePrefixes.ts` and
`src/server/authz/policies/management.ts`. D2's threshold (>=2 advisors, same anchor) fires. The
orchestrator resolves before Step 4, reviewers receive the facts, and the false CATASTROPHIC never
reaches them. **Build only what this counterfactual justifies — nothing more.**

---

## 3. Anforderungen

### R1 — Advisor ledger (`references/advisors.md`)

Insert into the **Common Preamble**, after the EVIDENCE CHAIN block (ends line 40:
`Any gap in the chain = [HYPOTHESIS]. ...`) and **before** `MATERIALITY:` (line 42):

- A prose requirement: every advisor ends its prose with an `UNTRACED LINKS:` line naming the file
  paths / symbols it reasoned about but could not read, or the literal `none`.
- The rule that an assumption about unshown code is `[HYPOTHESIS]`, never `[VERIFIED]`.

Add to the STRUCTURED OUTPUT field list (lines 86-94, the `Fields:` / `Each finding:` block) a
**top-level, advisor-level** key (NOT per-finding):

```
untraced_links (array of strings, [] when nothing was untraced) — file paths or symbols this
advisor reasoned about but could not read.
```

Rationale for top-level: the gap is a property of what the ADVISOR was shown, not of a single
finding. Several findings typically share one missing file.

### R2 — Coverage gate (`SKILL.md`, new Step 3.5)

Insert between Step 3 (line 437) and Step 4 (line 651) — i.e. at the end of Step 3, after the
"Post-cascade model resolution" block.

Behaviour:
1. Collect `untraced_links` from every responding advisor.
2. Normalise and count anchors. The same anchor reported by **>=2 advisors** is a **blocking
   coverage gap**.
3. For each blocking gap the orchestrator MUST do exactly one of:
   - **(a) Resolve** — read the named file and add its content, or a measured summary, to the
     substrate handed to reviewers and chairman, labelled as an orchestrator measurement taken
     after the advisors ran.
   - **(b) Forward** — if resolving is impossible or out of scope, state the gap explicitly in the
     reviewer AND chairman prompts, with the rule that findings depending on it may not be promoted
     above `[HYPOTHESIS]`.
4. Print `[Hydra] Coverage gate: {{N}} blocking gap(s) -- {{resolved|forwarded}}.`
5. **Never** auto-fetch files outside the review target's repo root; never widen scope silently.

Single-advisor (non-blocking) gaps are recorded and forwarded to the chairman only.

### R3 — Mechanical guard (`tests/unit/test_prompt_surface.py`)

The file holds 9 tests. Follow the established convention exactly:
- `ADVISORS = REPO / "references" / "advisors.md"` already exists at line 50.
- **Self-invalidation is mandatory.** See `test_common_preamble_has_no_unresolved_placeholders`
  (line 204) and especially its failure message at line 208: the guard asserts that its own anchor
  still exists and says so if not, instead of silently passing. A guard that can go green because
  its anchor vanished is worthless — this repo learned that the expensive way.

The new test asserts:
1. The Common Preamble carries the `UNTRACED LINKS:` requirement.
2. `untraced_links` appears in the structured-output field specification.
3. The anchor used to locate the preamble still exists (self-invalidation).

**Prove the guard by mutation:** delete the `UNTRACED LINKS:` line, run the test, confirm RED,
restore. A guard not proven red by mutation does not count as shipped.

### R4 — Sidecar consistency (`SKILL.md`)

`SKILL.md:954` instructs: *"shaped exactly as an `AdvisorFinding` (emit ONLY these keys, no
extras...)"* for `.findings.json`. That sentence is per-finding and `untraced_links` is
advisor-level, so there is **no direct conflict** — but the sidecar has no place to persist it.
Decide via Q1 below and, if persisting, update BOTH the schema block (lines 963-969) AND the
"no extras" sentence (line 954) in the same commit. Changing one and not the other reproduces
exactly the doc-vs-code divergence this very review found in the target project.

---

## 4. Technische Entscheidungen

**E1 — Structured field, not prose alone.** Prose already exists in spirit (`[HYPOTHESIS]` labels)
and demonstrably did NOT make the signal actionable. A machine-readable array is what a gate can
branch on.

**E2 — Threshold is >=2 advisors on the same anchor, not >=1.** A single advisor naming a file is
weak evidence and would fire on nearly every run, training the orchestrator to ignore the gate. Two
independent advisors converging on one missing anchor is the signal that actually correlated with a
real gap in the observed run — three converged there.

**E3 — The orchestrator resolves; Hydra never auto-fetches.** Automatic file loading would ship
un-disclosed sibling files to model providers — the exact class PR #45 closed. The gate raises the
flag; a supervised orchestrator step acts on it.

**E4 — The guard is mandatory, prose alone is not.** Measured in the 2026-07-29 session: prose-only
edits to this surface carry a roughly constant fix-of-fix rate, while mechanical guards are the one
edit type that does not. R3 is not optional polish.

### Bewusst ABGELEHNT (nicht erneut vorschlagen)

- **Auto-fetching untraced files** — see E3.
- **A 4th reviewer / another review round** — measured: all three reviewers shared one blind
  substrate and two of three amplified the same false finding. More of the same layer cannot fix a
  substrate defect.
- **A broad SKILL.md prose rewrite** — the fix-of-fix evidence forbids it. Minimal, anchored edits.
- **Making the gate HALT the run** — it must inform, not block; a hard stop trains the orchestrator
  to route around it.

---

## 5. Offene Fragen

- **Q1:** Persist `untraced_links` into `.findings.json`? Pro: the bench could then measure coverage
  quality across runs. Contra: touches the sidecar schema (`SKILL.md:963-969`) and the "no extras"
  sentence (line 954). **Recommendation: yes, as a top-level sibling of `findings`, not inside it.**
- **Q2:** Should the chairman prompt gain an explicit rule that a finding whose `untraced_links`
  anchor was never resolved cannot be rated CATASTROPHIC? Attractive — it is precisely what went
  wrong — but it adds prose to the chairman surface. **Recommendation: defer to a second PR; measure
  first.**
- **Q3:** Does `--no-review` change the gate? With no reviewers, gaps go straight to the chairman.
  The gate should still run. Confirm during implementation.

---

## 6. Arbeitsreihenfolge (für die frische Session)

1. `git -C ~/.claude/skills/hydra fetch -q origin && git log --oneline -1 origin/main` → expect
   `144be2c`. If it differs, **re-verify every anchor in section 3 before editing** — they are
   pinned to `144be2c`.
2. The branch already exists: `feat/advisor-untraced-links` (this spec is its first commit).
3. Implement R1 → R3 → R2, in that order. The guard (R3) before the gate (R2), so the guard is red
   first and can be proven by mutation.
4. Run and SHOW the output, checking exit codes separately — never through a pipe:
   ```bash
   cd ~/.claude/skills/hydra
   uv run --extra dev --extra bench --extra judge -- pytest tests/unit -q; echo "pytest_rc=$?"
   uv run --extra dev -- ruff check .; echo "ruff_rc=$?"
   uv run --extra dev -- mypy --strict hydra; echo "mypy_rc=$?"
   ```
   Baseline at `144be2c`: **373 tests green**, ruff and mypy clean. Expect 374+ after R3.
5. **Do not self-review this security-relevant prompt change.** Run one Codex reviewer over the diff
   (`/codex:rescue`, or codex-companion directly). Measured 2026-07-29: four self-review rounds found
   four defects and introduced three; one round by a different model found five that all four had
   missed. The first foreign round beats the fifth own round.
6. PR against `main`; squash only once CI is green. Branch protection is active (strict,
   `lint · types · unit tests`, enforce_admins, deliberately no review requirement).

---

## 7. Fallen aus der 2026-07-29-Session (real bezahlt)

- `cmd | tail -1` returns tail's status. Check exit codes separately.
- **zsh eats an unquoted `--include=*.ts`** — grep dies with "no matches found" while a trailing
  `head` still returns 0. Two greps in that session looked negative but never ran. Quote it:
  `--include='*.ts'`.
- A grep with no hits is not an all-clear until you have shown the pattern COULD have matched.
- A guard that turns red is information. The most valuable find of the prior session came from a
  WRONG guard draft. Understand the red before weakening it.
- Re-read every anchor from the file before editing — never from memory, and never from this spec
  alone.
- `git add -A` picks up untracked files. Check `git diff --cached --name-status` for `^A`.

---

## 8. Nach der Implementierung

Update this spec with what was learned, per project convention. If the counterfactual in section 2
turns out NOT to hold once implemented — i.e. the gate would not have caught the observed run — that
is itself a finding: say so and reconsider, rather than shipping the gate anyway.
