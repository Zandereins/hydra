"""Semgrep CLI wrapper for Hydra Phase 1 (§13.4)."""
from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hydra.envelopes import Severity, ToolFinding
from hydra.subprocess_safe import run_tool

_SEVERITY_MAP: dict[str, Severity] = {
    "ERROR": Severity.SERIOUS,
    "WARNING": Severity.MODERATE,
    "INFO": Severity.MINOR,
}

_MESSAGE_CAP = 500


@dataclass
class ToolResult:
    findings: list[ToolFinding] = field(default_factory=list)
    skipped: bool = False
    warnings: list[str] = field(default_factory=list)


def parse_semgrep_json(raw: dict[str, Any]) -> list[ToolFinding]:
    """Convert semgrep JSON output to ToolFinding list."""
    findings: list[ToolFinding] = []
    for r in raw.get("results", []):
        extra: dict[str, Any] = r.get("extra", {})
        sev_str: str = str(extra.get("severity", "WARNING")).upper()
        severity = _SEVERITY_MAP.get(sev_str, Severity.MODERATE)

        start_line: int = r.get("start", {}).get("line", 0)
        end_line: int = r.get("end", {}).get("line", start_line)
        lines = f"{start_line}-{end_line}" if start_line != end_line else str(start_line)

        raw_msg: str = str(extra.get("message", ""))
        message = raw_msg[:_MESSAGE_CAP]

        findings.append(
            ToolFinding(
                id=str(uuid.uuid4()),
                source="semgrep",
                rule_id=str(r.get("check_id", "")),
                file=r.get("path") or None,
                lines=lines,
                severity=severity,
                message=message,
            )
        )
    return findings


def run_semgrep(
    cwd: Path,
    changed_files: list[str],
    timeout: int = 120,
) -> ToolResult:
    """Run semgrep on changed_files; gracefully degrade on any failure."""
    result = ToolResult()

    if not shutil.which("semgrep"):
        result.skipped = True
        result.warnings.append("semgrep binary not found — skipping")
        return result

    argv = ["semgrep", "--json", "--config", "auto", *changed_files]

    try:
        proc = run_tool(argv, cwd=cwd, timeout=timeout)
    except TimeoutError as exc:
        result.skipped = True
        result.warnings.append(f"semgrep timed out: {exc}")
        return result

    # semgrep exits 0 (no findings) or 1 (findings found) — anything else is failure
    if proc.returncode not in (0, 1):
        result.skipped = True
        result.warnings.append(
            f"semgrep exited with code {proc.returncode}: {proc.stderr[:200]}"
        )
        return result

    try:
        raw: dict[str, Any] = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        result.skipped = True
        result.warnings.append(f"JSON parse failed: {exc}")
        return result

    result.findings = parse_semgrep_json(raw)
    return result
