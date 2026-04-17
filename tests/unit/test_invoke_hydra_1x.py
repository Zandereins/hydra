"""Tests for bench/runner/invoke_hydra_1x.py — guards against harness pre-flight regressions."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bench.runner.invoke_hydra_1x import apply_diff, invoke_hydra

# ---------------------------------------------------------------------------
# Bug 1: invoke_hydra must NOT pass --cwd to claude CLI
# ---------------------------------------------------------------------------


def test_invoke_hydra_argv_has_no_cwd_flag(tmp_path: Path) -> None:
    """--cwd is not a valid Claude Code CLI flag; subprocess cwd= must be used instead."""
    fake_report = tmp_path / ".hydra" / "reports" / "hydra-20260417-120000.md"
    fake_report.parent.mkdir(parents=True)
    fake_report.write_text("# report")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        invoke_hydra(tmp_path)

    call_args = mock_run.call_args
    argv: list[str] = call_args.args[0]
    assert "--cwd" not in argv, f"--cwd must not appear in argv; got: {argv}"


def test_invoke_hydra_uses_cwd_kwarg(tmp_path: Path) -> None:
    """subprocess.run must receive cwd= so the child process runs in the worktree."""
    fake_report = tmp_path / ".hydra" / "reports" / "hydra-20260417-120000.md"
    fake_report.parent.mkdir(parents=True)
    fake_report.write_text("# report")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        invoke_hydra(tmp_path)

    call_kwargs = mock_run.call_args.kwargs
    assert "cwd" in call_kwargs, "subprocess.run must receive cwd= kwarg"
    assert call_kwargs["cwd"] == str(tmp_path)


# ---------------------------------------------------------------------------
# Bug 2: apply_diff must raise on non-zero returncode
# ---------------------------------------------------------------------------


def test_apply_diff_raises_on_failure(tmp_path: Path) -> None:
    """A failed git-apply must not be silently swallowed — it wastes ~$0.60 per run."""
    diff_path = tmp_path / "case.patch"
    diff_path.write_text("--- /dev/null\n+++ /dev/null\n")

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["git", "apply"],
        )
        with pytest.raises((subprocess.CalledProcessError, RuntimeError)):
            apply_diff(tmp_path, diff_path)
