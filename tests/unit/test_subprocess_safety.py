from pathlib import Path

import pytest

from hydra.subprocess_safe import UnsafeArgError, run_tool


def test_runs_simple_command(tmp_path: Path) -> None:
    result = run_tool(["/bin/echo", "hello"], cwd=tmp_path, timeout=5)
    assert result.returncode == 0
    assert result.stdout.strip() == "hello"


def test_rejects_shell_metachar(tmp_path: Path) -> None:
    with pytest.raises(UnsafeArgError):
        run_tool(["/bin/echo", "foo; rm -rf /"], cwd=tmp_path, timeout=5)


def test_rejects_non_list_argv(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        run_tool("echo hello", cwd=tmp_path, timeout=5)  # type: ignore[arg-type]


def test_env_is_scrubbed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-leak-me")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "leak")
    result = run_tool(["/usr/bin/env"], cwd=tmp_path, timeout=5)
    assert "ANTHROPIC_API_KEY" not in result.stdout
    assert "AWS_SECRET_ACCESS_KEY" not in result.stdout
    assert "PATH=/usr/bin:/bin" in result.stdout


def test_timeout_raises(tmp_path: Path) -> None:
    with pytest.raises(TimeoutError):
        run_tool(["/bin/sleep", "5"], cwd=tmp_path, timeout=1)


def test_safe_fn_regex_accepts_normal_path(tmp_path: Path) -> None:
    # SAFE_FN: path-like args match r"^[A-Za-z0-9._/@:+=-]+$"
    result = run_tool(["/bin/echo", "src/foo_bar.py"], cwd=tmp_path, timeout=5)
    assert result.returncode == 0


def test_safe_fn_regex_rejects_backticks(tmp_path: Path) -> None:
    with pytest.raises(UnsafeArgError):
        run_tool(["/bin/echo", "`whoami`"], cwd=tmp_path, timeout=5)


def test_safe_fn_regex_rejects_dollar_paren(tmp_path: Path) -> None:
    with pytest.raises(UnsafeArgError):
        run_tool(["/bin/echo", "$(id)"], cwd=tmp_path, timeout=5)
