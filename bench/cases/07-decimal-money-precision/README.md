# Case 07 — Decimal Money Precision

A billing PR refactors `LineItem` to accept `price` as a decimal dollar string and
rewrites `calcSubtotal` to use `parseFloat` + IEEE 754 float accumulation, converting
to cents only at the end via `Math.round`. This silently corrupts invoice totals due
to floating-point rounding (e.g. summing 0.1 + 0.2 in a loop). A secondary issue is
that `parseFloat` returns `NaN` on malformed input with no guard, propagating silently.

**Ground truth:** 2 findings (1 mandatory, 1 optional). Plus 1 benign distractor.
**Category:** data.
**Expected position:** REJECT.
