"""Unit tests for hydra.phase1.tools.semgrep."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hydra.envelopes import Severity
from hydra.phase1.tools.semgrep import parse_semgrep_json, run_semgrep

# ---------------------------------------------------------------------------
# parse_semgrep_json — severity mapping
# ---------------------------------------------------------------------------


def test_parse_semgrep_error_maps_to_serious(tmp_path: Path) -> None:
    raw: dict[str, Any] = {
        "results": [
            {
                "check_id": "rule.sqli",
                "path": "app/db.py",
                "start": {"line": 10},
                "end": {"line": 12},
                "extra": {"severity": "ERROR", "message": "SQL injection"},
            }
        ]
    }
    findings = parse_semgrep_json(raw, tmp_path)
    assert len(findings) == 1
    assert findings[0].severity == Severity.SERIOUS
    assert findings[0].rule_id == "rule.sqli"
    assert findings[0].file == "app/db.py"
    assert findings[0].lines == "10-12"


def test_parse_semgrep_warning_maps_to_moderate(tmp_path: Path) -> None:
    raw: dict[str, Any] = {
        "results": [
            {
                "check_id": "rule.xss",
                "path": "app/views.py",
                "start": {"line": 5},
                "end": {"line": 5},
                "extra": {"severity": "WARNING", "message": "XSS risk"},
            }
        ]
    }
    findings = parse_semgrep_json(raw, tmp_path)
    assert findings[0].severity == Severity.MODERATE


def test_parse_semgrep_message_truncated_at_500(tmp_path: Path) -> None:
    long_msg = "x" * 600
    raw: dict[str, Any] = {
        "results": [
            {
                "check_id": "rule.long",
                "path": "a.py",
                "start": {"line": 1},
                "end": {"line": 1},
                "extra": {"severity": "WARNING", "message": long_msg},
            }
        ]
    }
    findings = parse_semgrep_json(raw, tmp_path)
    assert len(findings[0].message) <= 500


# ---------------------------------------------------------------------------
# Forward-compat: INFO → MINOR
# ---------------------------------------------------------------------------


def test_parse_semgrep_info_maps_to_minor(tmp_path: Path) -> None:
    raw: dict[str, Any] = {
        "results": [
            {
                "check_id": "x",
                "path": "a.py",
                "start": {"line": 1},
                "end": {"line": 1},
                "extra": {"severity": "INFO", "message": "note"},
            }
        ]
    }
    findings = parse_semgrep_json(raw, tmp_path)
    assert findings[0].severity == Severity.MINOR


# ---------------------------------------------------------------------------
# run_semgrep — graceful degrade on malformed JSON
# ---------------------------------------------------------------------------


def test_run_semgrep_malformed_json_returns_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/semgrep")
    # Path-validation now requires the file to exist before semgrep is invoked.
    (tmp_path / "a.py").write_text("# fixture")

    def fake_run_tool(*_a: object, **_k: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=0, stdout="not-json", stderr="")

    monkeypatch.setattr("hydra.phase1.tools.semgrep.run_tool", fake_run_tool)
    result = run_semgrep(tmp_path, changed_files=["a.py"])
    assert result.skipped is True
    # First warnings come from path validation (none expected); JSON parse
    # warning is the failure signal.
    assert any("JSON parse failed" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# A3-S1 / A3-S7 — argv injection + emitted-path containment hardening
# ---------------------------------------------------------------------------


def test_run_semgrep_rejects_traversal_in_changed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A3-S1: src/../../../etc/passwd must not reach semgrep argv."""
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/semgrep")
    captured_argv: list[list[str]] = []

    def fake_run_tool(argv: list[str], **_k: object) -> SimpleNamespace:
        captured_argv.append(argv)
        return SimpleNamespace(returncode=0, stdout='{"results":[]}', stderr="")

    monkeypatch.setattr("hydra.phase1.tools.semgrep.run_tool", fake_run_tool)
    result = run_semgrep(tmp_path, changed_files=["../../etc/passwd"])
    assert result.skipped is True
    assert any("unsafe/missing path" in w for w in result.warnings)
    assert captured_argv == [], "semgrep must not be invoked when all paths fail validation"


def test_run_semgrep_rejects_option_lookalike_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A3-S1: a file literally named --config=evil must not reach argv as a flag."""
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/semgrep")
    # File doesn't exist on disk → path validation rejects it (must_exist=True).
    captured_argv: list[list[str]] = []

    def fake_run_tool(argv: list[str], **_k: object) -> SimpleNamespace:
        captured_argv.append(argv)
        return SimpleNamespace(returncode=0, stdout='{"results":[]}', stderr="")

    monkeypatch.setattr("hydra.phase1.tools.semgrep.run_tool", fake_run_tool)
    result = run_semgrep(tmp_path, changed_files=["--config=http://evil/r"])
    assert result.skipped is True
    assert captured_argv == [], "semgrep must not see --config-lookalike argv"


def test_run_semgrep_argv_inserts_dash_dash_separator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A3-S1 belt-and-suspenders: `--` between config and paths so any
    POSIX-legal filename starting with `-` is parsed positionally."""
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/semgrep")
    (tmp_path / "legit.py").write_text("# fixture")
    captured_argv: list[list[str]] = []

    def fake_run_tool(argv: list[str], **_k: object) -> SimpleNamespace:
        captured_argv.append(argv)
        return SimpleNamespace(returncode=0, stdout='{"results":[]}', stderr="")

    monkeypatch.setattr("hydra.phase1.tools.semgrep.run_tool", fake_run_tool)
    run_semgrep(tmp_path, changed_files=["legit.py"])
    assert len(captured_argv) == 1
    argv = captured_argv[0]
    assert "--" in argv, f"expected -- separator in argv: {argv}"
    sep_idx = argv.index("--")
    assert argv[sep_idx - 1] == "auto", "-- must follow --config auto"
    assert argv[sep_idx + 1 :] == ["legit.py"], "validated paths must follow --"


def test_parse_semgrep_rejects_absolute_emitted_path(tmp_path: Path) -> None:
    """A3-S7: semgrep emitting `/etc/passwd` (e.g. via followed symlink) must
    not propagate as a `ToolFinding.file` value."""
    raw: dict[str, Any] = {
        "results": [
            {
                "check_id": "x",
                "path": "/etc/passwd",
                "start": {"line": 1},
                "end": {"line": 1},
                "extra": {"severity": "WARNING", "message": "outside repo"},
            }
        ]
    }
    findings = parse_semgrep_json(raw, tmp_path)
    assert findings[0].file is None


def test_parse_semgrep_rejects_traversal_emitted_path(tmp_path: Path) -> None:
    """A3-S7: a relative path that resolves outside cwd is also rejected."""
    raw: dict[str, Any] = {
        "results": [
            {
                "check_id": "x",
                "path": "../../etc/passwd",
                "start": {"line": 1},
                "end": {"line": 1},
                "extra": {"severity": "WARNING", "message": "outside repo"},
            }
        ]
    }
    findings = parse_semgrep_json(raw, tmp_path)
    assert findings[0].file is None
