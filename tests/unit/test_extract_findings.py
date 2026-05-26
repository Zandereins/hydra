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


REAL_REPORT = """<!-- hydra-integrity: sha256:abc session:HYDRA-x scope:body -->
---
hydra_version: "1.0"
top_actions:
  - id: A1
    severity: SERIOUS
    file: src/interceptors/auth.ts
    lines: 13-18
    summary: Gate forwarding on a destination allowlist
---

# Hydra Report: Axios Auth

## Actions

### A1 -- SERIOUS -- src/interceptors/auth.ts:13-18 -- Est: M

**What:** Inbound `Authorization` is forwarded onto every outbound request.
**Why:** Confused-deputy and credential-leak risk.
**How:** Gate on a destination allowlist.

### A2 -- SERIOUS -- src/interceptors/auth.ts:4-9 -- Est: S

**What:** `AuthConfig` declared but never used.
**Why:** Camouflages A1.
"""


def test_real_report_parses_body_actions_with_bug_text() -> None:
    # The live report leads with an integrity comment AND carries findings in the
    # `## Actions` body (`### A{N} -- SEV -- file:lines -- Est:`). Body text is
    # bug-descriptive (What/Why), unlike the fix-oriented frontmatter summary.
    cands = extract_from_report(REAL_REPORT)
    assert len(cands) == 2
    assert cands[0]["file"] == "src/interceptors/auth.ts"
    assert cands[0]["lines"] == "13-18"
    assert cands[0]["severity"] == "SERIOUS"
    assert "Authorization" in cands[0]["title"]
    assert "forwarded" in cands[0]["title"]


def test_em_dash_action_headings_parse() -> None:
    # Real reports vary the heading separator between ASCII `--` and em-dash `—`.
    md = (
        "## Actions\n\n"
        "### A1 — CRITICAL — src/plugins/rate-limit.ts:15,21-22 — Est: S\n\n"
        "**What:** async onRequest hook declares an unused done parameter.\n"
        "**Why:** Fastify hangs every request.\n"
    )
    cands = extract_from_report(md)
    assert len(cands) == 1
    assert cands[0]["file"] == "src/plugins/rate-limit.ts"
    assert cands[0]["lines"] == "15,21-22"
    assert "done" in cands[0]["title"]


def test_leading_integrity_comment_does_not_break_frontmatter_fallback() -> None:
    md = (
        "<!-- hydra-integrity: sha256:x session:y scope:body -->\n"
        "---\n"
        "top_actions:\n"
        "  - summary: CRLF injection\n"
        "    file: app.js\n"
        "    lines: '10-12'\n"
        "    severity: SERIOUS\n"
        "---\nbody\n"  # no ## Actions body -> falls back to frontmatter
    )
    cands = extract_from_report(md)
    assert cands[0]["file"] == "app.js"


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
        "position": "CONCERN", "file": "app.js", "lines": "10-12",
        "issue_class": "command_injection",
        "chain": {"premise": "p", "execution_trace": "", "conclusion": "c"},
    }]
    cands = extract_from_structured("\n".join(json.dumps(p) for p in payload))
    assert cands[0]["file"] == "app.js"
    assert cands[0]["issue_class"] == "command_injection"
    assert cands[0]["title"] == "CRLF"
