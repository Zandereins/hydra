# Case 08 — REST Response Contract Break

A PR to an Express user-route handler renames the `userId` field to `id` (and changes its type from `number` to `string`), drops the `email` field from `GET /users/:id`, and changes `GET /users` from returning a top-level array to a `{data:[...]}` envelope — all without API versioning. As a side effect it leaks `passwordHash` into the response. The `POST /users` route adds an optional `avatarUrl` field (backward-compatible distractor).

**Ground truth:** 3 findings (1 mandatory api_break, 2 optional). Plus 1 benign distractor.
**Category:** api.
**Expected position:** REJECT.
