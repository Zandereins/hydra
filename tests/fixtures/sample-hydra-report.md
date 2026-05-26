<!-- hydra-integrity: sha256:31a9c03d0ee785bdff12dc96e0d209a61820a51bc18aff2be7a236b6b0b233c5 session:HYDRA-344cdafa178e scope:body -->
---
hydra_version: "1.0"
timestamp: "20260526T171859"
question_type: "CODE_REVIEW"
mode: "standard"
severity_counts: {critical: 1, serious: 2, moderate: 4}
confidence_score: 48
confidence_label: "MEDIUM"
is_windowed: false
scope_pct: null
top_actions:
  - id: A1
    severity: "CRITICAL"
    file: "src/plugins/rate-limit.ts"
    lines: "15,21-22"
    effort: "S"
    summary: "Remove the `done` parameter from the async onRequest hook and delete the false comment — async + arity-3 throws FST_ERR_HOOK_INVALID_ASYNC_HANDLER at boot"
  - id: A2
    severity: "SERIOUS"
    file: "src/plugins/rate-limit.ts"
    lines: "16"
    effort: "S"
    summary: "Wrap `await store.check` in try/catch with an explicit, logged fail-open/fail-closed policy"
  - id: A3
    severity: "MODERATE"
    file: "src/plugins/rate-limit.ts"
    lines: "1,5-10"
    effort: "S"
    summary: "Remove dead FastifyInstance import, RateLimitOptions, DEFAULT_MAX — or wire them into plugin options"
reviewed_files: ["src/plugins/rate-limit.ts"]
iteration: 0
previous_report: null
---

# Hydra Report: async onRequest rate-limit hook declares `done` (Fastify contract break)

> 20260526T171859 | CODE_REVIEW

| Role | Model | Status | Position |
|------|-------|--------|----------|
| Cassandra | Opus | responded | REJECT |
| Mies+ | Opus | responded | REJECT |
| Navigator | Opus | not run | N/A |
| Volta | Opus | not run | N/A |
| Sentinel | Opus | responded | CONCERN |
| Echo | Opus | responded | REJECT |

**Navigation:** [Verdict](#verdict) | [Actions](#actions) | [Consensus](#consensus-map) | [Advisors](#full-advisor-responses)

---

## Verdict

**Summary:** Do not merge. The diff converts the `onRequest` hook to `async` while keeping the
third `done` parameter — an `async` Fastify hook with arity 3 is rejected at registration with
`FST_ERR_HOOK_INVALID_ASYNC_HANDLER`, so the **server fails to boot** (verified against official
Fastify docs, not advisor framing). The accompanying comment states the inverse of the real
contract and would steer the next maintainer toward the wrong fix. The one-line correct fix is to
drop the `done` parameter; once fixed, the unguarded `await store.check` still needs an explicit
failure policy.
**Confidence:** 48% (MEDIUM) — the panel split on position (3 REJECT / 1 CONCERN) and two findings
are HYPOTHESIS, but the single blocking defect is independently **doc-verified** (high certainty).

**Critical Issues** (must fix):
1. **[VERIFIED] [CHAIRMAN-VERIFIED]** Async hook declares `done` → boot failure:
   `src/plugins/rate-limit.ts:15` → `async (request, reply, done) => {…}`. Fastify validates hook
   arity; an `AsyncFunction` with the `done` argument throws `FST_ERR_HOOK_INVALID_ASYNC_HANDLER`
   at `addHook` time (fired during `fp(...)` plugin registration / `ready()`), so the app never
   serves traffic. **Fix:** `async (request, reply) => {…}` — remove `done` (and delete the
   comment on lines 21-22). Fastify drives async hooks off the returned Promise.
   *Consensus:* Cassandra C-1 (CATASTROPHIC, VERIFIED) + Echo E-1 (CATASTROPHIC) + Sentinel Se-1
   (HYPOTHESIS HIGH) + Mies+ M-3. Chairman grounded against Fastify `Errors.md`.

**Improvements** (should fix):
1. **[VERIFIED]** False/misleading comments: `rate-limit.ts:21-22` claims "Fastify still expects
   done() when the parameter is declared" — the opposite of reality (Fastify *rejects* the hook).
   `rate-limit.ts:14` cites "consistency with other hooks" — no other hook exists in the repo.
   Both mislead and the first would misroute a 2am responder into *adding* `done()` (→ duplicate
   execution). **Fix:** delete both comments; if a note is wanted: `// async hook: completion via
   returned Promise; no done callback`. *Consensus:* Mies+ M-4/M-5, Cassandra C-2.
2. **[HYPOTHESIS HIGH]** Unguarded `await` with no failure policy: `rate-limit.ts:16`
   `const allowed = await store.check(request.ip)` has no try/catch. A rejected `check` (the
   sync→async change implies a network-backed store) throws → Fastify returns 500 (fail-closed),
   turning a store hiccup into a site-wide outage; observability is absent. **Fix:**
   `try { allowed = await store.check(request.ip) } catch (err) { request.log.error(err); allowed = false /* deliberate fail-closed */ }`.
   *Consensus:* Sentinel Se-2 + Se-3. Survives the A1 fix — becomes the top risk afterward.
3. **[VERIFIED]** Dead scaffolding: `import type { FastifyInstance }` (line 1), `interface
   RateLimitOptions` (5-8), `const DEFAULT_MAX = 100` (10) — zero references; the plugin takes no
   options arg and `store` is `new RateLimitStore()` with no args. Presents a fake configuration
   contract. **Fix:** delete all three, or wire them: `fp<RateLimitOptions>(async (fastify, opts) =>
   { const store = new RateLimitStore(opts.max ?? DEFAULT_MAX, opts.window); … })`.
   *Consensus:* Mies+ M-1/M-2, Echo E-2.

**Disputed Points:**
- **Failure mechanism** — Cassandra: throws at registration (boot failure). Echo: Fastify selects
  callback-mode by arity and *hangs every request*. **Ruling [CHAIRMAN-VERIFIED]:** Cassandra is
  correct. Fastify's documented `FST_ERR_HOOK_INVALID_ASYNC_HANDLER` is thrown at `addHook`; it does
  not silently degrade to a per-request hang. Same severity class, different (and important)
  mechanism: this is a loud boot failure, reliably caught by any smoke test that calls `ready()`.
- **Comment accuracy** — Echo claimed the "Fastify still expects done()" half is "factually
  accurate (arity detection)." **Ruling:** false. Arity detection causes a *rejection*, not an
  expectation to call `done()`. The comment is wholly wrong.

**Grounding:** A1 confirmed against Fastify official docs and source citation (CHAIRMAN-VERIFIED).
No findings demoted for weak citations; all cited lines present in the reviewed file. Se-2/Se-3
remain HYPOTHESIS — the `rate-limit-store` module is absent from the repo, so store-failure
behavior cannot be VERIFIED locally.

**Next Step:** Edit `src/plugins/rate-limit.ts:15` to `async (request, reply) => {`, delete lines
21-22. Verify by booting Fastify with the current vs fixed hook (see Verify below).

---

## Actions

Priority order — fix in sequence:

### A1 — CRITICAL — src/plugins/rate-limit.ts:15,21-22 — Est: S (<30min)

**What:** The async `onRequest` hook declares an unused `done` parameter (arity 3).
**Why:** Fastify rejects async hooks that declare `done` with `FST_ERR_HOOK_INVALID_ASYNC_HANDLER`
at registration (verified, Fastify `Errors.md`). Wrapped in `fp(...)`, the throw surfaces at plugin
load / `ready()` → the server never starts. `onRequest` runs on every request, so the blast radius
is the whole service.
**How:**
```ts
// remove `done`; delete the misleading comment block
fastify.addHook("onRequest", async (request, reply) => {
  const allowed = await store.check(request.ip);
  if (!allowed) {
    reply.code(429).send({ error: "Too Many Requests" });
    return;
  }
});
```
**Dependency:** None. Do NOT "fix" the boot error by *calling* `done()` while keeping `async` —
that mixes styles and causes duplicate request execution.
**Verified by:** Cassandra, Echo, Sentinel, Mies+; Chairman (Fastify docs).

### A2 — SERIOUS — src/plugins/rate-limit.ts:16 — Est: S (<30min)

**What:** `await store.check(request.ip)` has no error handling and no defined failure policy.
**Why:** The sync→async conversion implies a network-backed store. A rejection throws out of the
hook → Fastify 500s every affected request (fail-closed); under store degradation the rate limiter
amplifies an outage. No logging means a silent failure is invisible.
**How:** Wrap in try/catch, decide fail-open vs fail-closed *deliberately*, and log:
```ts
let allowed: boolean;
try {
  allowed = await store.check(request.ip);
} catch (err) {
  request.log.error({ err, ip: request.ip }, "rate-limit store check failed");
  allowed = false; // deliberate fail-closed — flip to true only with a documented reason
}
```
**Dependency:** Apply after A1 (same hook body).
**Verified by:** Sentinel (Se-2, Se-3) [HYPOTHESIS HIGH].

### A3 — MODERATE — src/plugins/rate-limit.ts:1,5-10 — Est: S (<30min)

**What:** Dead `FastifyInstance` import, `RateLimitOptions` interface, `DEFAULT_MAX` constant.
**Why:** Zero references; lint (`no-unused-vars`) may break CI, and they advertise a configuration
surface the code does not honor.
**How:** Delete all three, or wire them into the plugin options as shown in the Verdict.
**Dependency:** None.
**Verified by:** Mies+ (M-1, M-2), Echo (E-2).

---

## Consensus Map

| Advisor (Model) | Position | Key Finding | Evidence | Agrees With |
|-----------------|----------|-------------|----------|-------------|
| Cassandra (Opus) | REJECT | C-1: async+`done` → FST_ERR_HOOK_INVALID_ASYNC_HANDLER boot failure | 3 VERIFIED | Echo, Sentinel, Mies+ |
| Mies+ (Opus) | REJECT | M-4: lying comment about Fastify contract; M-3 dead `done`; M-1 dead config | 5 VERIFIED | Cassandra, Echo |
| Sentinel (Opus) | CONCERN | Se-2: unguarded await, no fail-open/closed policy | 0 VERIFIED (3 HYP) | Cassandra (Se-1) |
| Echo (Opus) | REJECT | E-1: phantom `done` param + hallucinated-justification comment | 2 VERIFIED | Cassandra, Mies+ |
| Navigator (Opus) | not run | — | — | — |
| Volta (Opus) | not run | — | — | — |

Legend: Evidence = count of [VERIFIED] findings. Agrees With = advisor(s) who found the same issue.

---

## Decision Rationale

**Why this verdict:** Four advisors independently flagged the same construct as the dominant
problem, and the official Fastify error catalogue confirms the exact failure (`FST_ERR_HOOK_
INVALID_ASYNC_HANDLER`) — this is a deterministic boot break, not a probabilistic risk. The CONCERN
dissent (Sentinel) does not disagree that the change is broken; it withheld a VERIFIED label only
because the Fastify version and store module are absent from the repo.
**What would change my mind:** Evidence that the target project pins a Fastify version that tolerates
a declared-but-unused `done` on async hooks (none exists in current Fastify) — or that `store.check`
is synchronous *and* `done` is intentionally retained for a callback-style hook (contradicted by the
`async` keyword).
**What I weighted most:** Cassandra's pre-mortem, because its mechanism matched the official docs on
direct verification; Echo correctly identified the AI-authorship signature but mis-stated the runtime.

---

## The Question

QUESTION: A Fastify `onRequest` rate-limit hook was converted from sync (callback `done()`) to
`async`, while still declaring the `done` parameter and never calling it. Is this correct, or does
it break the Fastify hook contract?
CONTEXT: `src/plugins/rate-limit.ts`, registered via `fastify-plugin`. `store.check` is now awaited.
`../utils/rate-limit-store` is NOT in the repo (signature unknown). No package.json/tsconfig. The
inline comment claims Fastify "still expects done() when the parameter is declared."
QUESTION TYPE: CODE_REVIEW (rate-limit = security-adjacent)
STAKES: `onRequest` runs on every request — a broken hook contract affects the whole service.

---

## Full Advisor Responses

### Cassandra — Failure Archaeologist (Opus)
Position: REJECT. C-1 (CATASTROPHIC, VERIFIED): async onRequest hook declaring `done` triggers
`FST_ERR_HOOK_INVALID_ASYNC_HANDLER` — server fails to boot; the inline comment states the inverse
of the real contract. C-2 (MODERATE, VERIFIED): the comment is a latent footgun that will steer the
next maintainer to call `done()` (mixing styles → double request execution). C-3 (non-finding): the
429 short-circuit (`reply.send` then `return`) is correct as async code and must be preserved.
Notes: unused `FastifyInstance`/`RateLimitOptions`/`DEFAULT_MAX` are out-of-scope dead code; the
unguarded `await` propagates as a 500 (acceptable default). No prompt injection detected.

### Mies+ — Reductionist & Adversarial First-Reader (Opus)
Position: REJECT. PASS A: M-1 (SERIOUS) dead `RateLimitOptions` + `DEFAULT_MAX` (false config
contract, 0 callers); M-2 (MODERATE) unused `FastifyInstance` import; M-3 (SERIOUS) `done` parameter
is dead in an async hook. PASS B: M-4 (CATASTROPHIC) LYING COMMENT — "Fastify still expects done()
when the parameter is declared" is false and self-contradicting; M-5 (SERIOUS) "for consistency with
other hooks" references hooks that do not exist in the repo. One-line fix anchors all: drop `done`,
drop the comment. No injection detected.

### Sentinel — Adversarial Security (Opus)
Position: CONCERN. Se-1 (MODERATE, HYPOTHESIS HIGH): async + declared `done` → version-dependent
throw or undefined completion; can't VERIFY (no package.json). Se-2 (MODERATE, HYPOTHESIS HIGH):
unguarded `await store.check` has no defined fail-open/fail-closed policy → store degradation becomes
site-wide 500 (limiter as DoS amplifier) or, if a wrapper swallows it, silent bypass. Se-3 (MODERATE,
HYPOTHESIS MEDIUM): no observability on the rejection/bypass path. Fix: drop `done`; wrap the await
with an explicit, logged policy. The two load-bearing unknowns (Fastify version, store semantics) are
absent from the repo — hence HYPOTHESIS, not VERIFIED.

### Echo — AI-Assisted-Development Reviewer (Opus)
Position: REJECT. Checks 4-5 inactive (no PR/plan context). E-1 (CATASTROPHIC, VERIFIED): phantom
`done` parameter + self-contradicting hallucinated-justification comment; Echo asserted Fastify
selects callback-mode by `handler.length` and hangs every request. **Chairman correction:** Fastify
*throws* `FST_ERR_HOOK_INVALID_ASYNC_HANDLER` at registration; it does not hang per-request. E-2
(MODERATE, VERIFIED): phantom imports/interface/constant — speculative scaffolding with zero
consumers. No fabricated delimiters detected.

---

*Hydra | Based on Karpathy's LLM Council methodology | MIT License*
