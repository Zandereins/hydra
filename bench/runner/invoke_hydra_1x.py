"""Drive 1.x Hydra against each bench case workspace to capture baseline candidates."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess  # noqa: S404 — TODO(§18.4): route through run_tool once PATH handling is extended
import tempfile
from pathlib import Path
from typing import Any

from bench.runner.extract_findings import extract_candidates
from bench.runner.run_bench import (
    CASES_DIR,
    load_ground_truth,
    load_negative_anchors,
    write_baseline,
)
from bench.runner.scoring import score_case
from hydra.path_safety import PathEscapeError, contained_path

REPO_ROOT = Path(__file__).resolve().parents[2]
# Commit of Hydra 1.x to benchmark against. Override via HYDRA_1X_REF when
# re-pinning 1.x — the baseline JSON `label` and `commit_sha` track this.
COMMIT_SHA = os.environ.get("HYDRA_1X_REF", "3506f93")
HYDRA_1X_LABEL = f"hydra-1.x@{COMMIT_SHA}"
HYDRA_TIMEOUT_S = int(os.environ.get("HYDRA_TIMEOUT_S", "600"))

# Strict env ALLOWLIST for subprocesses exposed to untrusted workspace content (roadmap
# 1.1). The /hydra subprocess reviews attacker-influenceable code and the git calls run
# against an untrusted workspace; a denylist that strips only ANTHROPIC_* still forwards
# GH_TOKEN / AWS_* / every other secret into a prompt-injectable LLM session or a malicious
# .gitattributes clean-filter. Subscription auth lives under HOME (~/.claude), NOT in env,
# so a tight allowlist keeps the headless run working while denying secret exfiltration.
_ENV_ALLOW_EXACT = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "TERM", "TMPDIR", "TZ",
    "LANG", "LC_ALL", "LC_CTYPE",
})
_ENV_ALLOW_PREFIX = ("LC_", "CLAUDE_")  # locale categories + Claude Code's own (non-secret) config


def _allowed_subprocess_env() -> dict[str, str]:
    """Env for subprocesses exposed to untrusted workspace content: a strict allowlist.

    ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN are excluded by omission, which also keeps the
    Opus-heavy /hydra runs subscription-billed (ADR D-3.2) rather than flipping to per-token
    API billing. The ``CLAUDE_`` prefix forwards Claude Code's own config AND, deliberately,
    ``CLAUDE_CODE_OAUTH_TOKEN`` — the one auth secret we forward on purpose (see
    _headless_auth_env): it is the inference-only, revocable subscription token that lets the
    subprocess authenticate WITHOUT unlocking the macOS keychain."""
    return {
        k: v for k, v in os.environ.items()
        if k in _ENV_ALLOW_EXACT or k.startswith(_ENV_ALLOW_PREFIX)
    }


def _headless_auth_env() -> dict[str, str]:
    """Allowlisted env for the headless /hydra run, with the keychain-free auth credential
    enforced.

    Requires ``CLAUDE_CODE_OAUTH_TOKEN`` (from ``claude setup-token`` — auth precedence ABOVE
    the macOS keychain, billed to the subscription plan). Requiring it is the security fix for
    the keychain bypass: without the token `claude` falls back to the login keychain, which
    (a) raises a per-invocation unlock dialog across a multi-hour capture and (b) leaves the
    keychain UNLOCKED, exposing every other secret in it (gh/AWS/…) to this untrusted-
    workspace, prompt-injectable subprocess — defeating the env allowlist out-of-band. We fail
    fast rather than silently degrade into that. The token is inference-only and revocable
    (re-run ``claude setup-token`` to rotate)."""
    env = _allowed_subprocess_env()
    if not env.get("CLAUDE_CODE_OAUTH_TOKEN"):
        raise RuntimeError(
            "CLAUDE_CODE_OAUTH_TOKEN is not set. The headless /hydra subprocess needs it for "
            "subscription auth without the macOS keychain; without it `claude` triggers a "
            "per-invocation keychain unlock prompt and leaves the keychain unlocked to this "
            "untrusted-workspace subprocess. Run `claude setup-token` and export "
            "CLAUDE_CODE_OAUTH_TOKEN before the capture."
        )
    return env


def _git_env() -> dict[str, str]:
    """Hardened env for git run against an untrusted workspace: the allowlist + neutralised
    config sources. A workspace ``.gitattributes`` clean/smudge filter resolves its filter
    command from system/global gitconfig; pinning both to /dev/null (plus NOSYSTEM) closes
    that exfil/RCE vector. Commit identity is supplied via ``-c`` flags, so no gitconfig is
    needed; GIT_TERMINAL_PROMPT=0 avoids any credential-prompt hang."""
    env = _allowed_subprocess_env()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _validate_case_id(case_id: str) -> Path:
    """Resolve case_id inside CASES_DIR; raise on traversal, missing, or self-ref (A3-S5)."""
    try:
        resolved = contained_path(CASES_DIR, case_id, must_exist=False)
    except PathEscapeError as exc:
        raise RuntimeError(
            f"invalid case id (must resolve inside {CASES_DIR}): {case_id!r}"
        ) from exc
    # Reject "" / "." / "./." which all resolve to CASES_DIR itself: the caller
    # expects a named subdirectory, not the parent. Without this guard
    # `case_dir / "workspace"` would surface a confusing "no workspace/ dir"
    # error for a contract violation that should fail loudly here.
    if resolved == CASES_DIR.resolve():
        raise RuntimeError(f"empty/self-referential case id rejected: {case_id!r}")
    if not resolved.is_dir():
        raise RuntimeError(f"case directory does not exist: {case_id!r}")
    return resolved


def prepare_case_workspace(case_id: str) -> Path:
    """Copy case workspace to tmpdir, git-init, commit base, apply diff.

    Returns path to the initialized scratch dir with the case diff applied
    in the working tree (uncommitted) — so Hydra 1.x sees the PR diff.
    """
    case_dir = _validate_case_id(case_id)
    workspace_src = case_dir / "workspace"
    if not workspace_src.is_dir():
        raise RuntimeError(f"no workspace/ dir for case {case_id}")

    scratch = Path(tempfile.mkdtemp(prefix=f"hydra-case-{case_id}-"))
    # Any failure after mkdtemp (copytree, a git step, an unapplicable diff, or a
    # KeyboardInterrupt mid-capture) must remove the scratch dir — otherwise a 40-run
    # capture leaks one tmpdir per failed run. BaseException so Ctrl-C cleans up too.
    try:
        shutil.copytree(workspace_src, scratch, dirs_exist_ok=True)

        # Scrub any pre-existing .git/ before `git init` — workspace may ship
        # malicious .git/hooks/post-commit (or pre-commit, etc.) that `shutil.copytree`
        # preserves and `git init` does NOT overwrite. Without this, `git commit`
        # below executes attacker code as the user. Live RCE verified pre-fix.
        # Handle .git as directory, file (gitlink), or symlink — Iteration-2 F1.
        pre_git = scratch / ".git"
        if pre_git.is_symlink() or pre_git.is_file():
            pre_git.unlink()
        elif pre_git.is_dir():
            shutil.rmtree(pre_git)

        git_env = _git_env()
        for argv in (
            ["git", "init", "-q"],
            ["git", "add", "-A"],
            ["git", "-c", "user.email=bench@hydra.local", "-c", "user.name=bench",
             "commit", "-qm", "base"],
        ):
            subprocess.run(argv, cwd=scratch, check=True, env=git_env)

        diff_path = case_dir / "diff.patch"
        try:
            subprocess.run(
                ["git", "apply", "--whitespace=fix", str(diff_path)],
                cwd=scratch, check=True, env=git_env,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"git apply failed for {diff_path} in workspace {scratch}"
            ) from e
    except BaseException:
        shutil.rmtree(scratch, ignore_errors=True)
        raise

    return scratch


def invoke_hydra(workspace: Path) -> Path:
    """Run Claude Code headless with /hydra this in the workspace dir.

    `--settings '{"disableAllHooks": true}'` makes the run hermetic and
    reproducible: the operator's user-level hooks (e.g. a Stop hook that returns
    `{"decision":"block"}`) otherwise interrupt the headless session before the
    report is written → intermittent "no report produced". Hooks are disabled ONLY
    for this subprocess; CLAUDE.md/skills/plugins still load (unlike `--bare`), so
    we benchmark the real product. The operator's interactive sessions are untouched.
    """
    # The subprocess reviews untrusted workspace code, so it gets a strict env allowlist
    # (_headless_auth_env), NOT a denylist: GH_TOKEN/AWS_*/etc. must never reach a
    # prompt-injectable session. The allowlist also omits ANTHROPIC_API_KEY/AUTH_TOKEN,
    # which keeps these Opus-heavy /hydra runs subscription-billed (ADR D-3.2) — Claude Code
    # otherwise gives a present key precedence and flips to per-token API billing. Auth is the
    # CLAUDE_CODE_OAUTH_TOKEN (enforced by _headless_auth_env) so `claude` never reads the
    # macOS keychain — no unlock prompt, and the keychain stays locked (no out-of-band secret
    # exfil past the allowlist).
    subprocess.run(
        ["claude", "--print", "--settings", '{"disableAllHooks": true}', "/hydra this"],
        cwd=str(workspace),
        check=True,
        capture_output=True,
        text=True,
        timeout=HYDRA_TIMEOUT_S,
        env=_headless_auth_env(),
    )
    reports = sorted((workspace / ".hydra" / "reports").glob("hydra-*.md"))
    if not reports:
        raise RuntimeError(f"no report produced in {workspace}/.hydra/reports")
    return reports[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", nargs="*", default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "bench" / "baselines" / "hydra-1.x-2026-04-17.json",
    )
    args = parser.parse_args()

    case_ids = args.cases or [p.name for p in sorted(CASES_DIR.iterdir()) if p.is_dir()]

    scores_by_case: dict[str, Any] = {}
    for case_id in case_ids:
        workspace = prepare_case_workspace(case_id)
        try:
            report_path = invoke_hydra(workspace)
            candidates = extract_candidates(report_path)  # prefer .findings.json sidecar
            candidates_out = REPO_ROOT / "bench" / "runs" / "1x" / f"{case_id}.jsonl"
            candidates_out.parent.mkdir(parents=True, exist_ok=True)
            candidates_out.write_text("\n".join(json.dumps(c) for c in candidates))
            scores_by_case[case_id] = score_case(
                load_ground_truth(case_id),
                candidates,
                negative_anchors=load_negative_anchors(case_id),
            )
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    write_baseline(
        label=HYDRA_1X_LABEL,
        commit_sha=COMMIT_SHA,
        runs=[{"scores": scores_by_case}],
        output_path=args.output,
    )
    print(f"baseline → {args.output}")


if __name__ == "__main__":
    main()
