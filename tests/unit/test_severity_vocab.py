"""Regression guard: the report's severity vocabulary must match the Severity enum.

The prompt layer (SKILL.md, references/report-template.md) once drifted from
`hydra.envelopes.Severity`: advisors/Python emit CATASTROPHIC but the report counted a
`critical` bucket, so the worst-finding count was mis-keyed. This was silent — nothing
tested it. This guard pins the report-template's machine-readable `severity_counts`
buckets to the canonical enum so `critical` (not a Severity member) can't silently return.
"""
import re
from pathlib import Path

from hydra.envelopes import Severity

REPO = Path(__file__).resolve().parents[2]
REPORT_TEMPLATE = REPO / "references" / "report-template.md"


def test_report_template_severity_counts_match_enum() -> None:
    valid = {s.value.lower() for s in Severity}  # catastrophic, serious, moderate, minor, trivial
    assert "critical" not in valid, "guard premise: CRITICAL is not a Severity member"

    text = REPORT_TEMPLATE.read_text()
    m = re.search(r"severity_counts:\s*\{([^}]*)\}", text)
    assert m, "report-template lost its severity_counts frontmatter line"

    keys = re.findall(r"(\w+)\s*:", m.group(1))
    bad = [k for k in keys if k.lower() not in valid]
    assert not bad, (
        f"report-template severity_counts uses non-enum severities {bad}; "
        f"valid: {sorted(valid)}"
    )
