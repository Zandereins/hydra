"""Parse Hydra reports to candidate findings for bench scoring."""
from __future__ import annotations

from typing import Any

import yaml

from hydra.envelopes import AdvisorFinding


def extract_from_report(markdown: str) -> list[dict[str, Any]]:
    """Extract top_actions[] from a 1.x report's YAML frontmatter.

    1.x reports carry no issue_class — we deliberately omit it rather than emit
    a phantom 'other' that the scorer can never match (RECONCILE-2).
    """
    if not markdown.startswith("---"):
        return []
    end = markdown.find("\n---", 3)
    if end == -1:
        return []
    frontmatter = yaml.safe_load(markdown[3:end]) or {}
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
