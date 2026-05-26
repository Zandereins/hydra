"""Deterministic, non-LLM citation/grounding verification (spec Track-2 §2).

Pure synchronous helpers — no LLM, no network. Operates on the real
AdvisorFinding envelope (hydra/envelopes.py); the spec §5.1 reference to
`chain.code_construct` is stale (RECONCILE-1) — token source is
title + chain.premise + chain.conclusion.
"""
from __future__ import annotations

import re
from pathlib import Path

from hydra.envelopes import AdvisorFinding, Severity

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


_STOPWORDS = frozenset({
    "the", "and", "for", "with", "into", "from", "this", "that", "when",
    "where", "value", "values", "code", "function", "method", "via", "use",
    "used", "uses", "can", "could", "will", "would", "should", "enables",
})
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
MAX_TOKENS = 8


def extract_salient_tokens(finding: AdvisorFinding, *, max_tokens: int = MAX_TOKENS) -> list[str]:
    """Identifiers / call names from title + chain.premise + chain.conclusion.

    RECONCILE-1: spec §5.1's `chain.code_construct` does not exist; the real
    free-text code-claim fields are title + premise + conclusion.
    """
    source = " ".join([finding.title, finding.chain.premise, finding.chain.conclusion])
    seen: list[str] = []
    for match in _TOKEN_RE.findall(source):
        if match.lower() in _STOPWORDS:
            continue
        if match not in seen:
            seen.append(match)
        if len(seen) >= max_tokens:
            break
    return seen


def count_present(tokens: list[str], text: str) -> int:
    """How many tokens appear (case-insensitive substring) in text."""
    lowered = text.lower()
    return sum(1 for t in tokens if t.lower() in lowered)


# Full ladder (spec §5.1). NOTE divergence: the shipped *prompt* Grounding-Lite
# floors at MODERATE because its vocab is coarser; the deterministic check uses
# all five rungs with a TRIVIAL floor.
_SEVERITY_LADDER: tuple[Severity, ...] = (
    Severity.CATASTROPHIC,
    Severity.SERIOUS,
    Severity.MODERATE,
    Severity.MINOR,
    Severity.TRIVIAL,
)


def demote(severity: Severity) -> Severity:
    """Drop exactly one rung; TRIVIAL is the floor."""
    idx = _SEVERITY_LADDER.index(severity)
    return _SEVERITY_LADDER[min(idx + 1, len(_SEVERITY_LADDER) - 1)]
