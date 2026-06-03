# Case 30 — weak PRNG for a password-reset token (CWE-330)

**Origin:** hand-crafted (synthetic). Not derived from any real/private codebase.

**Scenario:** `diff.patch` adds `generateResetToken`, which builds the single-use
password-reset token from concatenated `Math.random()` hex digits. A non-cryptographic
PRNG makes the token predictable → an attacker can forge a valid reset link and take
over the account. This is an unambiguous true CWE-330 a competent reviewer must flag.

**Role in the crypto-FN over-suppression re-test (PR #22 caveat):** the *enumerated
floor* / positive control. The SELECTIVITY clause literally lists "password-reset code",
so a flag here confirms the harness, the `claude --print` transport, and the control arm
reliably elicit a real CWE-330. Expected near-ceiling; it does **not** carry the closure
claim (case 31 does).

Mandatory finding: the `Math.random` line inside `generateResetToken` (post-patch
line derived from the prepared workspace, see `expected_findings.jsonl`).
