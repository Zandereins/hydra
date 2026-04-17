"""Single subprocess entrypoint. Never call subprocess.run directly elsewhere."""
from __future__ import annotations

import asyncio
import re
import subprocess
from pathlib import Path

SHELL_METACHARS = re.compile(r"[;&|`$<>\n\r]")
SAFE_FN = re.compile(r"^[A-Za-z0-9._/@:+=-]+$")
ALLOWED_ENV_KEYS = {"PATH", "LANG", "HOME", "TMPDIR"}
SCRUBBED_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}


class UnsafeArgError(Exception):
    """Argument contains shell metacharacters or fails SAFE_FN."""


def _validate_args(argv: list[str]) -> None:
    if not isinstance(argv, list):
        raise TypeError(f"argv must be list[str], got {type(argv).__name__}")
    for arg in argv:
        if SHELL_METACHARS.search(arg):
            raise UnsafeArgError(f"shell metacharacter in arg: {arg!r}")
        if ("/" in arg or arg.startswith(".")) and not SAFE_FN.fullmatch(arg):
            raise UnsafeArgError(f"path-like arg fails SAFE_FN: {arg!r}")


def run_tool(
    argv: list[str],
    cwd: Path,
    timeout: int = 120,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run subprocess with shell=False, scrubbed env, timeout, arg validation."""
    _validate_args(argv)
    env = dict(SCRUBBED_ENV)
    if extra_env:
        for k, v in extra_env.items():
            if k in ALLOWED_ENV_KEYS or k.startswith("HYDRA_"):
                env[k] = v
    try:
        return subprocess.run(
            argv,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"{argv[0]} exceeded {timeout}s timeout"
        ) from exc


async def run_tool_async(
    argv: list[str],
    cwd: Path,
    timeout: int = 120,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Async wrapper — runs run_tool in a thread (GIL releases during wait)."""
    return await asyncio.to_thread(run_tool, argv, cwd, timeout, extra_env)
