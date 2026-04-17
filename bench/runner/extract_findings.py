"""Parse 1.x report markdown to candidate findings for bench scoring."""
from __future__ import annotations

from typing import Any

import yaml


def extract_from_report(markdown: str) -> list[dict[str, Any]]:
    """Extract top_actions[] from report frontmatter as candidate findings."""
    if not markdown.startswith("---"):
        return []
    end = markdown.find("\n---", 3)
    if end == -1:
        return []
    frontmatter = yaml.safe_load(markdown[3:end])
    actions = frontmatter.get("top_actions", []) or []

    def _to_class(severity: str) -> str:
        # 1.x reports don't carry issue_class; always map to "other".
        return "other"

    candidates: list[dict[str, Any]] = []
    for a in actions:
        candidates.append({
            "title": a.get("summary", ""),
            "file": a.get("file"),
            "lines": str(a.get("lines", "")),
            "severity": a.get("severity", "MODERATE"),
            "issue_class": _to_class(a.get("severity", "")),
            "position": "CONCERN",
        })
    return candidates
