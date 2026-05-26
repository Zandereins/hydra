import json

from bench.runner.extract_findings import extract_from_report, extract_from_structured

SAMPLE_REPORT = """---
hydra_version: "1.0"
severity_counts:
  critical: 0
  serious: 1
  moderate: 0
top_actions:
  - id: A1
    severity: SERIOUS
    file: src/interceptors/auth.ts
    lines: 14-28
    effort: small
    summary: Unvalidated Authorization header forwarded
---

## Verdict
REQUEST CHANGES: one SERIOUS finding unresolved.

## Actions

### A1 — Unvalidated Authorization header forwarded
**What:** Forwarded without validation.
**Severity:** SERIOUS
**File:** src/interceptors/auth.ts:14-28
"""


def test_extract_from_report_yields_top_actions() -> None:
    findings = extract_from_report(SAMPLE_REPORT)
    assert len(findings) == 1
    f = findings[0]
    assert f["file"] == "src/interceptors/auth.ts"
    assert f["lines"] == "14-28"
    assert f["severity"] == "SERIOUS"
    assert "Authorization" in f["title"]


def test_one_x_candidate_omits_default_issue_class() -> None:
    md = (
        "---\n"
        "top_actions:\n"
        "  - summary: CRLF injection\n"
        "    file: app.js\n"
        "    lines: '10-12'\n"
        "    severity: SERIOUS\n"
        "---\nbody\n"
    )
    cands = extract_from_report(md)
    # 1.x carries no real class -> do not emit a phantom 'other' that can never match
    assert "issue_class" not in cands[0] or cands[0]["issue_class"] is None
    assert cands[0]["file"] == "app.js"


def test_structured_extractor_reads_advisor_findings() -> None:
    payload = [{
        "id": "f1", "title": "CRLF", "severity": "SERIOUS", "evidence": "VERIFIED",
        "position": "CONCERN", "file": "app.js", "lines": "10-12", "issue_class": "command_injection",
        "chain": {"premise": "p", "execution_trace": "", "conclusion": "c"},
    }]
    cands = extract_from_structured("\n".join(json.dumps(p) for p in payload))
    assert cands[0]["file"] == "app.js"
    assert cands[0]["issue_class"] == "command_injection"
    assert cands[0]["title"] == "CRLF"
