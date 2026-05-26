"""Deterministic, non-LLM citation/grounding verification (spec Track-2 §2).

Pure synchronous helpers — no LLM, no network. Operates on the real
AdvisorFinding envelope (hydra/envelopes.py); the spec §5.1 reference to
`chain.code_construct` is stale (RECONCILE-1) — token source is
title + chain.premise + chain.conclusion.
"""
from __future__ import annotations

from pathlib import Path

DEFAULT_MAX_LINES = 200  # DoS cap: never read more than this many lines for one citation


def _parse_line_range(lines: str) -> tuple[int, int] | None:
    """Parse a citation range string ('N' or 'N-M', 1-indexed inclusive)."""
    s = lines.strip()
    if not s:
        return None
    try:
        if "-" in s:
            a_str, b_str = s.split("-", 1)
            a, b = int(a_str), int(b_str)
        else:
            a = b = int(s)
    except ValueError:
        return None
    if a < 1 or b < a:
        return None
    return a, b


def read_range(path: Path, lines: str, *, max_lines: int = DEFAULT_MAX_LINES) -> str | None:
    """Return the cited source lines joined by '\\n', or None if unresolvable.

    Bounds-checks the range against the file and caps the number of lines read
    (DoS guard against a malicious `lines: "1-99999999"`).
    """
    parsed = _parse_line_range(lines)
    if parsed is None:
        return None
    start, end = parsed
    end = min(end, start + max_lines - 1)
    selected: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for idx, line in enumerate(fh, start=1):
            if idx < start:
                continue
            if idx > end:
                break
            selected.append(line.rstrip("\n"))
    return "\n".join(selected) if selected else None
