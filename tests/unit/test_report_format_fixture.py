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


def test_extracts_candidates_from_real_captured_report() -> None:
    cands = extract_from_report(FIXTURE.read_text())
    assert len(cands) >= 1, "real report yielded no candidates — report format drifted"
    for c in cands:
        assert c["file"], "candidate missing file"
        assert c["lines"], "candidate missing lines"
        assert c["title"], "candidate missing bug-descriptive title"
