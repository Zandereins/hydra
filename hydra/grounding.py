"""Deterministic, non-LLM citation/grounding verification (spec Track-2 §2).

Pure synchronous helpers — no LLM, no network. Operates on the real
AdvisorFinding envelope (hydra/envelopes.py); the spec §5.1 reference to
`chain.code_construct` is stale (RECONCILE-1) — token source is
title + chain.premise + chain.conclusion.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from hydra.envelopes import AdvisorFinding, GroundingStatus, Position, Severity
from hydra.line_spec import parse_line_spans
from hydra.path_safety import PathEscapeError, contained_path

DEFAULT_MAX_LINES = 200  # DoS cap: never read more than this many lines for one citation
DEFAULT_MAX_LINE_BYTES = 4096  # DoS cap: bound bytes per line (pathological minified files)


def _parse_line_range(lines: str) -> tuple[int, int] | None:
    """Parse a 1-indexed line spec to (min_start, max_end) for the grounder's window.

    Delegates the grammar to the shared :func:`hydra.line_spec.parse_line_spans` (single
    source of truth) and collapses the sub-spans to the enclosing window. Returns None when
    nothing parses — e.g. '' / 'abc' / a lone reversed span — so callers demote a finding
    whose citation cannot be located.
    """
    spans = parse_line_spans(lines)
    if not spans:
        return None
    return min(s for s, _ in spans), max(e for _, e in spans)


def read_range(
    path: Path,
    lines: str,
    *,
    max_lines: int = DEFAULT_MAX_LINES,
    max_line_bytes: int = DEFAULT_MAX_LINE_BYTES,
) -> str | None:
    """Return the cited source lines joined by '\\n', or None if unresolvable.

    Bounds-checks the range against the file and caps BOTH the line count and the
    bytes read (spec §6): a hard ceiling of ``max_lines * max_line_bytes`` chars is
    read regardless of line structure, so a pathological single-line (minified) file
    cannot be slurped whole. Each returned line is itself truncated to max_line_bytes.
    """
    parsed = _parse_line_range(lines)
    if parsed is None:
        return None
    start, end = parsed
    end = min(end, start + max_lines - 1)
    selected: list[str] = []
    idx = 0
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        # Stream line-by-line with a per-line byte cap: readline(max_line_bytes+1) reads
        # at most that many chars OR up to the newline. This is correct for far-off cited
        # lines (no whole-prefix buffering) AND bounds memory on a pathological single-line
        # (minified) file — neither the old line-iterator nor the bulk-read+split did both.
        while idx < end:
            piece = fh.readline(max_line_bytes + 1)
            if not piece:
                break
            idx += 1
            if not piece.endswith("\n"):
                # line longer than the cap (or EOF): drain the rest of the physical line
                # without buffering it, so one giant line can't be slurped into memory.
                while True:
                    rest = fh.readline(max_line_bytes + 1)
                    if not rest or rest.endswith("\n"):
                        break
            if idx >= start:
                selected.append(piece.rstrip("\n")[:max_line_bytes])
    return "\n".join(selected) if selected else None


_STOPWORDS = frozenset({
    "the", "and", "for", "with", "into", "from", "this", "that", "when",
    "where", "value", "values", "code", "function", "method", "via", "use",
    "used", "uses", "can", "could", "will", "would", "should", "enables",
})
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
MAX_TOKENS = 8


def salient_tokens_from_text(source: str) -> list[str]:
    """Up to MAX_TOKENS distinct identifier-like tokens from free text (stopwords
    excluded). Shared by the finding extractor and the bench threshold sweep so the
    calibrated CITATION_THRESHOLD is computed over the SAME tokenization the live
    grounder uses."""
    seen: list[str] = []
    for match in _TOKEN_RE.findall(source):
        if match.lower() in _STOPWORDS:
            continue
        if match not in seen:
            seen.append(match)
        if len(seen) >= MAX_TOKENS:
            break
    return seen


def extract_salient_tokens(finding: AdvisorFinding) -> list[str]:
    """Up to MAX_TOKENS identifiers / call names from title + chain.premise + conclusion.

    RECONCILE-1: spec §5.1's `chain.code_construct` does not exist; the real
    free-text code-claim fields are title + premise + conclusion.
    """
    return salient_tokens_from_text(
        " ".join([finding.title, finding.chain.premise, finding.chain.conclusion])
    )


def count_present(tokens: list[str], text: str) -> int:
    """How many tokens appear in text as whole words (case-insensitive).

    Word-boundary (not raw substring) so a short token like 'err' does not spuriously
    match inside 'logger'/'stderr' — that over-matching inflated false CITATION_PRESENT.
    """
    lowered = text.lower()
    return sum(
        1 for t in tokens if re.search(rf"\b{re.escape(t.lower())}\b", lowered)
    )


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


CITATION_THRESHOLD = 0.325  # CALIBRATED (Track-3 P5, spec §6): F1-maximizing value of a
#   TP/FP sweep over bench/grounding_labels.jsonl — separates the highest hallucinated
#   citation (0.286) from the lowest genuine one (0.375). Re-derived + drift-guarded by
#   tests/unit/test_threshold_calibration.py (was an uncalibrated 0.4, which over-demoted
#   genuine citations near the boundary). Re-sweep if the label set changes.

_SAFETY_POSITIONS = frozenset({Position.APPROVE})
_SAFETY_SEVERITIES = frozenset({Severity.TRIVIAL})


def ground_finding(
    finding: AdvisorFinding,
    repo_root: Path | str,
    *,
    threshold: float = CITATION_THRESHOLD,
) -> AdvisorFinding:
    """Set finding.grounding (and demote severity where required) in place."""
    if finding.position in _SAFETY_POSITIONS or finding.severity in _SAFETY_SEVERITIES:
        finding.grounding = GroundingStatus.NOT_APPLICABLE
        return finding

    if not finding.file or not finding.lines:
        finding.grounding = GroundingStatus.NO_CITATION
        finding.severity = demote(finding.severity)
        return finding

    try:
        # must_exist=False: run the escape check first so PATH_ESCAPE always takes
        # precedence over FILE_MISSING, even for paths that both escape and are absent.
        resolved = contained_path(repo_root, finding.file, must_exist=False)
    except PathEscapeError:
        finding.grounding = GroundingStatus.PATH_ESCAPE  # caller drops to degradation panel
        return finding

    if not resolved.exists():
        finding.grounding = GroundingStatus.FILE_MISSING
        finding.severity = demote(finding.severity)
        return finding

    try:
        range_text = read_range(resolved, finding.lines)
    except OSError:  # race / permission / unreadable between exists() and open()
        range_text = None
    if range_text is None:
        finding.grounding = GroundingStatus.RANGE_MISSING
        finding.severity = demote(finding.severity)
        return finding

    tokens = extract_salient_tokens(finding)
    ratio = count_present(tokens, range_text) / max(len(tokens), 1)
    if ratio >= threshold:
        finding.grounding = GroundingStatus.CITATION_PRESENT
    else:
        finding.grounding = GroundingStatus.TOKEN_MISMATCH
        finding.severity = demote(finding.severity)
    return finding


_DEMOTED_STATUSES = frozenset({
    GroundingStatus.NO_CITATION,
    GroundingStatus.FILE_MISSING,
    GroundingStatus.RANGE_MISSING,
    GroundingStatus.TOKEN_MISMATCH,
})


@dataclass(frozen=True)
class GroundingSummary:
    total: int
    citation_present: int
    not_applicable: int
    demoted: int
    dropped: int
    demoted_breakdown: dict[str, int] = field(default_factory=dict)
    unknown: int = 0  # findings never grounded (default status) — should be 0 after a full run

    def render(self) -> str:
        pct = (100.0 * self.citation_present / self.total) if self.total else 0.0
        demoted_line = f"- Auto-demoted: {self.demoted}"
        parts = [f"{n} {status}" for status, n in sorted(self.demoted_breakdown.items()) if n]
        if parts:
            demoted_line += f" ({', '.join(parts)})"
        unknown_line = f"\n- ⚠ UNGROUNDED (UNKNOWN): {self.unknown}" if self.unknown else ""
        return (
            "## Grounding Summary\n"
            f"- Findings total: {self.total}\n"
            f"- CITATION_PRESENT: {self.citation_present} ({pct:.1f}%)\n"
            f"- NOT_APPLICABLE (safety claim): {self.not_applicable}\n"
            f"{demoted_line}\n"
            f"- Dropped (PATH_ESCAPE): {self.dropped}"
            f"{unknown_line}"
        )


def summarize(findings: list[AdvisorFinding]) -> GroundingSummary:
    breakdown = {
        status.value: sum(1 for f in findings if f.grounding == status)
        for status in _DEMOTED_STATUSES
    }
    return GroundingSummary(
        total=len(findings),
        citation_present=sum(
            1 for f in findings if f.grounding == GroundingStatus.CITATION_PRESENT
        ),
        not_applicable=sum(
            1 for f in findings if f.grounding == GroundingStatus.NOT_APPLICABLE
        ),
        demoted=sum(1 for f in findings if f.grounding in _DEMOTED_STATUSES),
        dropped=sum(1 for f in findings if f.grounding == GroundingStatus.PATH_ESCAPE),
        demoted_breakdown=breakdown,
        unknown=sum(1 for f in findings if f.grounding == GroundingStatus.UNKNOWN),
    )
