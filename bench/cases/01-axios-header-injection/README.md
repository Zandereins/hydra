# Case 01 — Axios Header Injection

A trusted HTTP client forwards the caller's `Authorization` header
verbatim to a downstream service without validating the scheme or
confirming the caller is entitled to forward credentials.

**Ground truth:** 2 findings — 1 mandatory SERIOUS (`auth_bypass`, the forwarded credential) + 1 optional MINOR (`secret_exposure`, credential logged). Plus a benign distractor (`Math.random` correlation id).
**Category:** security.
**Expected position:** REJECT.
