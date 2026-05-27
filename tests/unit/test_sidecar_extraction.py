"""Track-3 Component A — structured `.findings.json` sidecar extraction."""
from pathlib import Path

from bench.runner.extract_findings import (
    extract_candidates,
    extract_from_sidecar,
    sidecar_path_for,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sample-hydra.findings.json"
# A REAL sidecar captured live in the P6 pilot — its issue_class values are free-text
# ("credential smuggling", "dead code", ...), not the strict IssueClass enum. The first
# extractor rejected every such finding; this fixture guards against that regression.
REAL_FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "sample-hydra-real-freetext.findings.json"
)


def test_sidecar_fixture_yields_candidates() -> None:
    cands = extract_from_sidecar(FIXTURE.read_text())
    assert len(cands) == 2
    assert cands[0]["file"] == "src/plugins/rate-limit.ts"
    assert cands[0]["lines"] == "15,21-22"
    assert cands[0]["issue_class"] == "api_break"
    assert "done" in cands[0]["title"]


def test_sidecar_wrong_schema_version_returns_empty() -> None:
    assert extract_from_sidecar('{"schema_version": "9.9", "findings": []}') == []


def test_sidecar_malformed_json_returns_empty_not_crash() -> None:
    assert extract_from_sidecar("{not json") == []


def test_sidecar_real_freetext_issue_class_is_extracted() -> None:
    # P6-pilot regression: the live skill emits free-text issue_class — all findings must
    # still be extracted (the strict AdvisorFinding validation used to drop every one).
    cands = extract_from_sidecar(REAL_FIXTURE.read_text())
    assert len(cands) == 6
    assert cands[0]["file"] == "src/interceptors/auth.ts"
    assert "smuggling" in cands[0]["title"].lower()
    assert cands[0]["issue_class"] == "credential smuggling"  # free-text preserved verbatim


def test_sidecar_skips_only_anchorless_findings() -> None:
    # lenient contract: a finding is dropped ONLY when it lacks a file+lines anchor
    # (unusable for scoring); extra keys / free-text fields are tolerated, not rejected.
    text = (
        '{"schema_version": "1.0", "findings": ['
        '{"id":"A1","title":"no anchor","severity":"SERIOUS","issue_class":"whatever"},'
        '{"id":"A2","title":"valid","severity":"MODERATE","file":"b.ts","lines":"2",'
        '"issue_class":"free text class","BONUS_FIELD":1}'
        "]}"
    )
    cands = extract_from_sidecar(text)
    assert [c["file"] for c in cands] == ["b.ts"]  # anchorless A1 dropped, A2 (extra key) kept
    assert cands[0]["issue_class"] == "free text class"


def test_extract_candidates_prefers_sidecar_over_prose(tmp_path: Path) -> None:
    report = tmp_path / "hydra-20260526T000000-x.md"
    report.write_text(
        "## Actions\n\n### A1 -- SERIOUS -- from_prose.ts:1 -- Est: S\n**What:** prose bug.\n"
    )
    sidecar_path_for(report).write_text(FIXTURE.read_text())
    cands = extract_candidates(report)
    # sidecar wins -> rate-limit.ts candidates, not from_prose.ts
    assert {c["file"] for c in cands} == {"src/plugins/rate-limit.ts"}


def test_extract_candidates_falls_back_to_prose_when_no_sidecar(tmp_path: Path) -> None:
    report = tmp_path / "hydra-20260526T000000-y.md"
    report.write_text(
        "## Actions\n\n### A1 -- SERIOUS -- from_prose.ts:1 -- Est: S\n**What:** prose bug.\n"
    )
    cands = extract_candidates(report)
    assert cands[0]["file"] == "from_prose.ts"
