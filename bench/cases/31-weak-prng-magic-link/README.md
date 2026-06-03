# Case 31 — weak PRNG for a magic sign-in link (CWE-330, non-enumerated)

**Origin:** hand-crafted (synthetic). Not derived from any real/private codebase.

**Scenario:** the base workspace ships a *benign* cache-buster (`assetUrl`, line 5 — a
non-security `Math.random` that must **not** be flagged). `diff.patch` adds
`createMagicSignInLink`, whose link identifier is minted from `Math.random() + Date.now()`.
Possession of that identifier grants one-click account access, so a predictable value is
account takeover (CWE-330).

**Why non-enumerated:** the source never uses the words *token / secret / nonce / session /
csrf / reset*. The security relevance must be **inferred** from the access semantics (an
in-source comment and the `auth/verify?lid=` URL make this unambiguous). A flag therefore
proves real selectivity reasoning, not keyword echo of the clause's enumerated examples.

**Role in the crypto-FN over-suppression re-test (PR #22 caveat):** the *real test*.
Engineered off-ceiling (harder to attribute than the enumerated reset-token) so the control
arm has headroom and over-suppression has somewhere to show. This case carries the closure
claim.

**Pre-registered unambiguity (before any billed run):** a possession-equals-login sign-in
link minted from a non-CSPRNG is an unambiguous true CWE-330. A treatment no-flag here is
genuine over-suppression, not correct selectivity. This is fixed in writing and is not
renegotiable post-hoc.

Mandatory finding: the `Math.random` line inside `createMagicSignInLink` (post-patch line
derived from the prepared workspace). Negative anchor: the `assetUrl` cache-buster.
