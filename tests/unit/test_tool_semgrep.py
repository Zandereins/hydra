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


def test_parse_semgrep_error_maps_to_serious() -> None:
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
    findings = parse_semgrep_json(raw)
    assert len(findings) == 1
    assert findings[0].severity == Severity.SERIOUS
    assert findings[0].rule_id == "rule.sqli"
    assert findings[0].file == "app/db.py"
    assert findings[0].lines == "10-12"


def test_parse_semgrep_warning_maps_to_moderate() -> None:
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
    findings = parse_semgrep_json(raw)
    assert findings[0].severity == Severity.MODERATE


def test_parse_semgrep_message_truncated_at_500() -> None:
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
    findings = parse_semgrep_json(raw)
    assert len(findings[0].message) <= 500


# ---------------------------------------------------------------------------
# Forward-compat: INFO → MINOR
# ---------------------------------------------------------------------------


def test_parse_semgrep_info_maps_to_minor() -> None:
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
    findings = parse_semgrep_json(raw)
    assert findings[0].severity == Severity.MINOR


# ---------------------------------------------------------------------------
# run_semgrep — graceful degrade on malformed JSON
# ---------------------------------------------------------------------------


def test_run_semgrep_malformed_json_returns_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/semgrep")

    def fake_run_tool(*_a: object, **_k: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=0, stdout="not-json", stderr="")

    monkeypatch.setattr("hydra.phase1.tools.semgrep.run_tool", fake_run_tool)
    result = run_semgrep(tmp_path, changed_files=["a.py"])
    assert result.skipped is True
    assert "JSON parse failed" in result.warnings[0]
