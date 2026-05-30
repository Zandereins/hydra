# Case 02 — Prisma N+1 Query

A refactor replaces a single `findMany({ include: { posts: true } })` call
with a loop that issues one `prisma.post.findMany()` per user. For N users
this produces N+1 database round trips instead of 1, causing severe
throughput degradation under any meaningful load.

**Ground truth:** 2 findings — 1 mandatory MODERATE (`performance_degradation`, the N+1 loop) + 1 optional MINOR (`performance_degradation`, unbounded user fetch). Plus a benign distractor (single COUNT aggregate).
**Category:** perf.
**Expected position:** CONCERN.
