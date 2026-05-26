# Case 06 — Node.js Async Rate-Limit Race (TOCTOU)

The PR adds an audit-log write to `incrementAndCheck`, converting it from a synchronous function to an `async` one and inserting `await persistAuditEvent(...)` between the `entry.count >= MAX_REQUESTS` guard and the `entry.count += 1` write. This yield point lets two concurrent requests for the same IP both read the stale count, both pass the limit check, and both increment — doubling the effective rate-limit cap. The API signature change (sync → async) is also a silent breaking change: callers that do not await the result receive a truthy `Promise` object and the rate limit is bypassed entirely.

**Ground truth:** 3 findings (1 mandatory race_condition, 2 optional). Plus 1 benign distractor.
**Category:** concurrency.
**Expected position:** REJECT
