"""Per-run nonce + <<UNTRUSTED_*>> wrapper helpers."""
from __future__ import annotations

import re
import secrets

UNTRUSTED_RE = re.compile(
    r"<<UNTRUSTED_[A-Za-z_]+_[0-9a-f]{6}>>.*?<<END_UNTRUSTED_[A-Za-z_]+_[0-9a-f]{6}>>",
    re.DOTALL,
)


def mint_nonce() -> str:
    """6-hex-char nonce (48 bits). Minted at Phase 0; reused through the run."""
    return secrets.token_hex(3)


def wrap_untrusted(kind: str, nonce: str, body: str) -> str:
    """Wrap untrusted content with per-run-tagged delimiters.

    `kind` examples: PR_DIFF, PR_DESCRIPTION, TOOL_OUTPUT_SEMGREP,
                     ADVISOR_OUTPUT_cassandra, CONFIG_JSON.
    """
    return f"<<UNTRUSTED_{kind}_{nonce}>>{body}<<END_UNTRUSTED_{kind}_{nonce}>>"
