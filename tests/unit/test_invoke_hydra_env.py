"""Env hardening for the bench subprocesses that touch untrusted workspace content.

The /hydra subprocess reviews attacker-influenceable code; the git calls run against an
untrusted workspace. Both must receive a strict env *allowlist* (not a denylist that only
strips ANTHROPIC_*), so GH_TOKEN / AWS_* / other secrets can never reach a prompt-injectable
LLM session or a workspace .gitattributes clean-filter (roadmap 1.1)."""
from __future__ import annotations

import os

import pytest

from bench.runner.invoke_hydra_1x import _allowed_subprocess_env, _git_env


def test_allowlist_keeps_runtime_essentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("HOME", "/home/x")
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    env = _allowed_subprocess_env()
    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/home/x"  # subscription auth lives under HOME — must survive
    assert env["LANG"] == "en_US.UTF-8"


def test_allowlist_drops_secrets_and_stays_plan_billed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("GH_TOKEN", "ghp_secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws_secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok")
    env = _allowed_subprocess_env()
    assert "GH_TOKEN" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert "ANTHROPIC_API_KEY" not in env  # excluded by omission -> run stays plan-billed
    assert "ANTHROPIC_AUTH_TOKEN" not in env


def test_allowlist_keeps_claude_and_locale_prefixes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/c")
    monkeypatch.setenv("LC_CTYPE", "UTF-8")
    env = _allowed_subprocess_env()
    assert env["CLAUDE_CONFIG_DIR"] == "/c"  # Claude Code's own config (not a secret)
    assert env["LC_CTYPE"] == "UTF-8"


def test_git_env_neutralises_external_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("GH_TOKEN", "ghp_secret")
    env = _git_env()
    # system + global gitconfig are the clean/smudge-filter injection vector -> neutralise
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_CONFIG_GLOBAL"] == os.devnull
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert "GH_TOKEN" not in env  # git subprocess also gets the strict allowlist
    assert env["PATH"] == "/usr/bin"
