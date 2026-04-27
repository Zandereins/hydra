"""Semgrep CLI wrapper for Hydra Phase 1 (§13.4)."""
from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hydra.envelopes import Severity, ToolFinding
from hydra.path_safety import PathEscapeError, contained_path
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


def _safe_relative_path(cwd: Path, raw_path: str) -> str | None:
    """Validate a semgrep-emitted path is inside cwd; return as relative or None.

    A3-S7: semgrep can emit absolute paths (e.g., when scanning followed
    symlinks) or paths that escape the scan root. Treating them as
    `ToolFinding.file` would mislead downstream grounding/report code into
    opening files outside the user's repo. Reject silently to None and let
    the caller surface a warning if needed.
    """
    try:
        resolved = contained_path(cwd, raw_path, must_exist=False)
    except PathEscapeError:
        return None
    try:
        return str(resolved.relative_to(cwd.resolve()))
    except ValueError:
        return None


def parse_semgrep_json(raw: dict[str, Any], cwd: Path) -> list[ToolFinding]:
    """Convert semgrep JSON output to ToolFinding list.

    `cwd` is the scan root; emitted paths are validated against it (A3-S7).
    """
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

        raw_path = r.get("path")
        file_field: str | None = (
            _safe_relative_path(cwd, raw_path) if isinstance(raw_path, str) else None
        )

        findings.append(
            ToolFinding(
                id=str(uuid.uuid4()),
                source="semgrep",
                rule_id=str(r.get("check_id", "")),
                file=file_field,
                lines=lines,
                severity=severity,
                message=message,
            )
        )
    return findings


def _validate_input_paths(cwd: Path, changed_files: list[str]) -> tuple[list[str], list[str]]:
    """Validate each input path is inside cwd. Return (valid_relpaths, warnings).

    A3-S1: filenames like `--config=http://evil/r` or `src/../../../etc/passwd`
    pass `subprocess_safe._validate_args` (SHELL_METACHARS doesn't catch `=`,
    SAFE_FN allows `=` and `/`). Without `contained_path` validation, semgrep
    would either fetch a remote rule config or scan a file outside the repo.
    """
    valid: list[str] = []
    warnings: list[str] = []
    for f in changed_files:
        try:
            resolved = contained_path(cwd, f, must_exist=True)
        except (PathEscapeError, FileNotFoundError) as exc:
            warnings.append(f"skipping unsafe/missing path {f!r}: {exc}")
            continue
        try:
            valid.append(str(resolved.relative_to(cwd.resolve())))
        except ValueError:  # pragma: no cover — contained_path guarantees this works
            warnings.append(f"skipping path that escaped root after resolve: {f!r}")
    return valid, warnings


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

    valid_paths, path_warnings = _validate_input_paths(cwd, changed_files)
    result.warnings.extend(path_warnings)
    if not valid_paths:
        result.skipped = True
        result.warnings.append("no valid paths to scan after containment check")
        return result

    # `--` separator: any validated path that happens to start with `-`
    # (POSIX-legal filename) must be parsed by semgrep as a positional path,
    # not as a flag. A3-S1 belt-and-suspenders.
    argv = ["semgrep", "--json", "--config", "auto", "--", *valid_paths]

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

    result.findings = parse_semgrep_json(raw, cwd)
    return result
