"""Parse Hydra reports to candidate findings for bench scoring."""
from __future__ import annotations

import re
from typing import Any

import yaml

from hydra.envelopes import AdvisorFinding

# Real reports prepend a `<!-- hydra-integrity: ... -->` line before the YAML
# frontmatter; strip it so `startswith("---")` works (verified against a live report).
_INTEGRITY_RE = re.compile(r"\A<!--.*?-->[ \t]*\n", re.DOTALL)
# Body action heading: `### A1 -- SERIOUS -- src/interceptors/auth.ts:13-18 -- Est: M`
_ACTION_RE = re.compile(
    r"^###\s+A\d+\s+--\s+(?P<sev>[A-Z]+)\s+--\s+(?P<loc>.+?)\s+--\s+Est:",
    re.MULTILINE,
)
# Bug-descriptive lines inside an action block (What/Why) — best for must_mention.
_FIELD_RE = re.compile(r"\*\*(?:What|Why):\*\*\s*(.+)")


def _split_loc(loc: str) -> tuple[str, str]:
    """Split 'path/to/file.ts:13-18' into (file, lines); lines may be ''."""
    loc = loc.strip().strip("`")
    if ":" in loc:
        file, lines = loc.rsplit(":", 1)
        return file.strip(), lines.strip()
    return loc, ""


def _from_actions_body(markdown: str) -> list[dict[str, Any]]:
    """Parse `## Actions` body headings — the format-stable finding source.

    The What/Why text is bug-descriptive (unlike the fix-oriented frontmatter
    summary), so must_mention keyword matching works against it.
    """
    candidates: list[dict[str, Any]] = []
    matches = list(_ACTION_RE.finditer(markdown))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        block = markdown[m.end() : end]
        file, lines = _split_loc(m.group("loc"))
        text = " ".join(fm.group(1).strip() for fm in _FIELD_RE.finditer(block))
        candidates.append({
            "title": text or m.group("loc").strip(),
            "file": file,
            "lines": lines,
            "severity": m.group("sev"),
        })
    return candidates


def _from_frontmatter(markdown: str) -> list[dict[str, Any]]:
    """Fallback: top_actions[] from YAML frontmatter (fix-oriented summary)."""
    md = _INTEGRITY_RE.sub("", markdown, count=1)
    if not md.startswith("---"):
        return []
    end = md.find("\n---", 3)
    if end == -1:
        return []
    frontmatter = yaml.safe_load(md[3:end]) or {}
    actions = frontmatter.get("top_actions", []) or []
    return [
        {
            "title": a.get("summary", ""),
            "file": a.get("file"),
            "lines": str(a.get("lines", "")),
            "severity": a.get("severity", "MODERATE"),
        }
        for a in actions
    ]


def extract_from_report(markdown: str) -> list[dict[str, Any]]:
    """Candidate findings from a Hydra report.

    Primary = `## Actions` body headings (bug-descriptive What/Why); falls back to
    frontmatter top_actions[] when no body actions exist. 1.x carries no issue_class
    — omitted rather than emit a phantom 'other' the scorer can't match (RECONCILE-2).
    """
    return _from_actions_body(markdown) or _from_frontmatter(markdown)


def extract_from_structured(jsonl: str) -> list[dict[str, Any]]:
    """Extract candidates from a 2.0 AdvisorFinding JSONL (grounding CLI output)."""
    candidates: list[dict[str, Any]] = []
    for line in jsonl.splitlines():
        if not line.strip():
            continue
        f = AdvisorFinding.model_validate_json(line)
        candidates.append({
            "title": f.title,
            "file": f.file,
            "lines": f.lines or "",
            "severity": f.severity.value,
            "issue_class": f.issue_class.value,
        })
    return candidates
