"""Per-run nonce + <<UNTRUSTED_*>> wrapper helpers.

UNTRUSTED_RE: detection regex for trusted-zone boundaries. It enforces
matching `kind` and `nonce` between open and close tags via backreferences,
so forged close tags with a different nonce will NOT prematurely close
a wrapper.
"""
from __future__ import annotations

import re
import secrets

# Single owner of the run-nonce width (48-bit). Every consumer — the regex below,
# mint_nonce, the wrap_untrusted validator, and hydra.envelopes' pydantic patterns —
# derives from this, so the width can never drift across modules (it once did:
# conftest + a token_hex(3)/"48 bits" docstring). 12 hex matches SKILL.md `openssl rand -hex 6`.
NONCE_HEX_LEN = 12
_NONCE_RE = rf"[0-9a-f]{{{NONCE_HEX_LEN}}}"

# Single owner of the KIND alphabet — the UNTRUSTED_RE detector and the wrap_untrusted
# validator (_KIND_PATTERN) MUST derive from one source, exactly as the nonce width derives
# from NONCE_HEX_LEN. Otherwise they drift: a kind wrap_untrusted accepts but UNTRUSTED_RE
# cannot re-detect (e.g. a digit-bearing TOOL_OUTPUT_SHA256 / OSV_V2) yields a syntactically
# valid wrapper that the boundary detector silently misses — the trusted-zone boundary fails
# OPEN. First char excludes digits (identifier rule); later chars allow them. The close tag
# still repeats the exact kind+nonce via backreference, so digits/underscores never create an
# ambiguous parse that could shift the nonce.
_KIND_RE_SRC = r"[A-Za-z_][A-Za-z0-9_]*"

UNTRUSTED_RE = re.compile(
    rf"<<UNTRUSTED_(?P<kind>{_KIND_RE_SRC})_(?P<nonce>{_NONCE_RE})>>"
    r".*?"
    r"<<END_UNTRUSTED_(?P=kind)_(?P=nonce)>>",
    re.DOTALL,
)

_KIND_PATTERN = re.compile(rf"^{_KIND_RE_SRC}$")


def mint_nonce() -> str:
    """12-hex-char nonce (48 bits). Minted at Phase 0; reused through the run.

    48 bits matches SKILL.md's interactive boundary token (`openssl rand -hex 6`).
    The prior 24-bit width (token_hex(3)) collided ~3% at N=1000 (birthday)."""
    return secrets.token_hex(NONCE_HEX_LEN // 2)


def wrap_untrusted(kind: str, nonce: str, body: str) -> str:
    """Wrap untrusted content with per-run-tagged delimiters.

    `kind` examples: PR_DIFF, PR_DESCRIPTION, TOOL_OUTPUT_SEMGREP,
                     ADVISOR_OUTPUT_cassandra, CONFIG_JSON.
    """
    if not _KIND_PATTERN.fullmatch(kind):
        raise ValueError(
            f"kind must match {_KIND_PATTERN.pattern!r}, got {kind!r}"
        )
    if not re.fullmatch(_NONCE_RE, nonce):
        raise ValueError(f"nonce must be {NONCE_HEX_LEN} hex chars, got {nonce!r}")
    return f"<<UNTRUSTED_{kind}_{nonce}>>{body}<<END_UNTRUSTED_{kind}_{nonce}>>"
