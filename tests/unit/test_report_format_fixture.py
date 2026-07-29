"""Format-drift guard: a real captured Hydra report must keep parsing.

The bench's `claude --print /hydra this` path is cost-gated and not unit-tested, so a
silent change to the report format (the kind that once broke extract_from_report:
leading `<!-- hydra-integrity -->` comment + `## Actions` body headings) would only
surface in a costly live run. This fixture is a real captured report; if the format
drifts so the extractor stops finding candidates, CI fails here instead.
"""
from pathlib import Path

from bench.runner.extract_findings import extract_from_report

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sample-hydra-report.md"


FIXTURE_ACTION_COUNT = 3  # `### A1..A3` in sample-hydra-report.md — pinned, not a lower bound


def test_extracts_candidates_from_real_captured_report() -> None:
    """Guards the What/Why parser, which the previous assertions could not reach.

    `assert c["title"]` was vacuous: `_from_actions_body` sets `title = text or loc`, so with
    `_FIELD_RE` fully broken every title falls back to `f"{file}:{lines}"` — non-empty, and the
    test passed. Proven by mutation: replacing `_FIELD_RE` with a never-matching pattern left this
    file green while every title silently degraded to its own location string, which is what the
    scorer matches `must_mention` keywords against — so real `critical_recall` would go 1.00 -> 0.00
    with CI none the wiser.

    Two changes close it: the count is pinned rather than `>= 1` (at `>= 1`, two of three actions
    could stop parsing unnoticed), and each title must differ from its own `file:lines`, which is
    exactly the fallback value.
    """
    cands = extract_from_report(FIXTURE.read_text())
    assert len(cands) == FIXTURE_ACTION_COUNT, (
        f"fixture yielded {len(cands)} candidates, expected {FIXTURE_ACTION_COUNT} — the report "
        "format drifted, or an action stopped parsing. Do not relax this to `>= 1`."
    )
    for c in cands:
        assert c["file"], "candidate missing file"
        assert c["lines"], "candidate missing lines"
        assert c["title"] != f"{c['file']}:{c['lines']}", (
            f"candidate title fell back to its own location ({c['title']!r}) — the What/Why "
            "parser is not matching, so the bug-descriptive text the scorer keys on is gone"
        )
