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
# Reports use either ASCII `--` or em/en-dash (`—`/`–`) as the separator — accept all.
_DASH = r"(?:--|—|–)"
_ACTION_RE = re.compile(
    rf"^###\s+A\d+\s+{_DASH}\s+(?P<sev>[A-Z]+)\s+{_DASH}\s+(?P<loc>.+?)\s+{_DASH}\s+Est:",
    re.MULTILINE,
)
# Bug-descriptive lines inside an action block (What/Why), multi-line until the next
# **Field:** / blank line / end — real reports wrap these across several lines.
_FIELD_RE = re.compile(r"\*\*(?:What|Why):\*\*\s*(.+?)(?=\n\*\*|\n\n|\Z)", re.DOTALL)
# A line-spec is digits with optional commas/dashes/space ("13", "13-18", "15,21-22").
_LINESPEC_RE = re.compile(r"^\d[\d,\s-]*$")


def _actions_section(markdown: str) -> str:
    """Slice just the `## Actions` section (heading → next `## ` or EOF).

    Scopes heading parsing so `### A{N}`-shaped lines elsewhere (e.g. advisor prose
    in `## Full Advisor Responses`) can't be mistaken for action candidates.
    """
    head = re.search(r"^##\s+Actions\s*$", markdown, re.MULTILINE)
    if head is None:
        return ""
    rest = markdown[head.end() :]
    nxt = re.search(r"^##\s+", rest, re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def _split_loc(loc: str) -> tuple[str, str]:
    """Split 'path/to/file.ts:13-18' into (file, lines); lines may be ''.

    Only treats the rsplit tail as a line-spec if it actually looks like one, so a
    Windows-style or colon-bearing path with no line range isn't mis-split.
    """
    loc = loc.strip().strip("`")
    if ":" in loc:
        file, lines = loc.rsplit(":", 1)
        lines = lines.strip()
        if _LINESPEC_RE.match(lines):
            return file.strip(), lines
    return loc, ""


def _from_actions_body(markdown: str) -> list[dict[str, Any]]:
    """Parse `## Actions` body headings — the format-stable finding source.

    The What/Why text is bug-descriptive (unlike the fix-oriented frontmatter
    summary), so must_mention keyword matching works against it.
    """
    section = _actions_section(markdown)
    candidates: list[dict[str, Any]] = []
    matches = list(_ACTION_RE.finditer(section))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section)
        block = section[m.end() : end]
        file, lines = _split_loc(m.group("loc"))
        # collapse each multi-line What/Why to single-spaced text for keyword matching
        text = " ".join(" ".join(fm.group(1).split()) for fm in _FIELD_RE.finditer(block))
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
    try:  # LLM-emitted YAML may be malformed — degrade to no candidates, never crash
        frontmatter = yaml.safe_load(md[3:end])
    except yaml.YAMLError:
        return []
    if not isinstance(frontmatter, dict):
        return []
    actions = frontmatter.get("top_actions", [])
    if not isinstance(actions, list):
        return []
    return [
        {
            "title": a.get("summary", ""),
            "file": a.get("file"),
            "lines": str(a.get("lines", "")),
            "severity": a.get("severity", "MODERATE"),
        }
        for a in actions
        if isinstance(a, dict)
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
