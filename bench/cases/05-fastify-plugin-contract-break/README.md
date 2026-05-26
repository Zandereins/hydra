# Case 05 — Fastify Plugin Contract Break

The diff converts a callback-style `onRequest` hook to an `async` function
while keeping the `done` parameter in the signature. In Fastify, if `done`
is declared as a parameter the framework expects it to be called; when it
is not, Fastify waits indefinitely, hanging every incoming request. The
misleading comment in the diff ("done() must not be called") creates a
false sense of correctness while violating the plugin contract.

**Ground truth:** 3 findings — 1 mandatory MODERATE (`api_break`, async hook omits `done()`) + 2 optional (`other`, `request.ip` without trustProxy; `other`, dead `RateLimitOptions`/`DEFAULT_MAX`). Plus a benign distractor (`Math.floor` fixed-window bucket).
**Category:** api.
**Expected position:** CONCERN.
