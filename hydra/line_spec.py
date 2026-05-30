"""Shared parser for citation line specs — the single source of truth.

A *line spec* is a comma-separated list of 1-indexed spans, each either a single line
(``"142"``), a range (``"142-158"``), or a mix (``"15,21-22"``). Real Hydra citations use
all three forms. Both the deterministic grounder (:mod:`hydra.grounding`) and the bench
scorer (:mod:`bench.runner.scoring`) parse this grammar; they share this one implementation
so the two cannot drift apart (they previously had divergent copies — different return
shapes AND different handling of malformed input).

Semantics are **fail-soft per sub-span**: an invalid sub-span (non-integer, zero/negative,
or reversed) is dropped and the remaining valid spans are returned. Callers map an empty
result to their own "unparseable" outcome (grounding -> None, scoring -> no overlap).
"""
from __future__ import annotations

MAX_LINE_SPANS = 32  # DoS cap: bound the comma-spans parsed from one citation


def parse_line_spans(spec: str, *, max_spans: int = MAX_LINE_SPANS) -> list[tuple[int, int]]:
    """Parse ``spec`` into ``(start, end)`` pairs (1-indexed, inclusive).

    At most ``max_spans`` comma-separated parts are considered. Invalid sub-spans are
    dropped fail-soft; the valid ones are returned in order (possibly empty)."""
    spans: list[tuple[int, int]] = []
    for part in spec.split(",")[:max_spans]:
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                a_str, b_str = part.split("-", 1)
                a, b = int(a_str), int(b_str)
            else:
                a = b = int(part)
        except ValueError:
            continue  # non-integer sub-span -> drop it (fail-soft)
        if a < 1 or b < a:
            continue  # zero/negative/reversed -> drop it
        spans.append((a, b))
    return spans
