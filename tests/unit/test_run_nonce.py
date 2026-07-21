import re

from hydra.run_nonce import UNTRUSTED_RE, mint_nonce, wrap_untrusted

# 48-bit run nonce = 12 hex chars (token_hex(6)), matching SKILL.md's interactive
# boundary token (`openssl rand -hex 6`). 24-bit (6 hex) collided ~3% at N=1000.
_NONCE = "abc123def456"


def test_mint_nonce_format() -> None:
    nonce = mint_nonce()
    assert re.fullmatch(r"[0-9a-f]{12}", nonce)  # 48 bits


def test_mint_nonce_unique_across_calls() -> None:
    # 48-bit nonce — collisions are negligible for any realistic sample
    # (birthday at N=1000: ~1.8e-9, vs ~3% at the old 24-bit width).
    samples = {mint_nonce() for _ in range(1000)}
    assert len(samples) == 1000


def test_wrap_untrusted_emits_correct_tags() -> None:
    out = wrap_untrusted("PR_DIFF", _NONCE, "diff --git a/x b/x\n")
    assert out.startswith(f"<<UNTRUSTED_PR_DIFF_{_NONCE}>>")
    assert out.endswith(f"<<END_UNTRUSTED_PR_DIFF_{_NONCE}>>")


def test_untrusted_re_matches_wrapped_block() -> None:
    wrapped = wrap_untrusted("ADVISOR_OUTPUT_cassandra", _NONCE, "finding")
    assert UNTRUSTED_RE.search(wrapped) is not None


def test_untrusted_re_rejects_mismatched_nonce() -> None:
    forged = "<<UNTRUSTED_KIND_aaaaaaaaaaaa>>body<<END_UNTRUSTED_KIND_bbbbbbbbbbbb>>"
    assert UNTRUSTED_RE.search(forged) is None


def test_untrusted_re_rejects_mismatched_kind() -> None:
    forged = "<<UNTRUSTED_KINDA_aaaaaaaaaaaa>>body<<END_UNTRUSTED_KINDB_aaaaaaaaaaaa>>"
    assert UNTRUSTED_RE.search(forged) is None


def test_untrusted_re_matches_multiline_body() -> None:
    wrapped = wrap_untrusted("PR_DIFF", _NONCE, "line1\nline2\nline3")
    assert UNTRUSTED_RE.search(wrapped) is not None


def test_untrusted_re_detects_every_kind_wrap_untrusted_accepts() -> None:
    # Single-source contract: UNTRUSTED_RE's kind alphabet MUST accept every kind
    # wrap_untrusted's validator (_KIND_PATTERN) accepts — including digit-bearing kinds
    # (a future TOOL_OUTPUT_SHA256 / OSV_V2). If the detector's alphabet is narrower, a
    # syntactically valid wrapper becomes silently undetectable and the trusted-zone
    # boundary fails OPEN. Guards the run_nonce.py:21/27 alphabet drift.
    for kind in ("TOOL_OUTPUT_SEMGREP", "SHA256", "OSV_V2", "PR_DIFF_V2", "TOOL_OUTPUT_OSV2"):
        wrapped = wrap_untrusted(kind, _NONCE, "body")
        assert UNTRUSTED_RE.search(wrapped) is not None, f"undetectable kind: {kind}"


def test_wrap_untrusted_rejects_bad_kind() -> None:
    import pytest
    with pytest.raises(ValueError, match="kind must match"):
        wrap_untrusted("BAD>>INJECT", _NONCE, "body")


def test_wrap_untrusted_rejects_bad_nonce() -> None:
    import pytest
    with pytest.raises(ValueError, match="nonce must be 12 hex"):
        wrap_untrusted("PR_DIFF", "XXXXXXXXXXXX", "body")


def test_wrap_untrusted_rejects_old_24bit_nonce() -> None:
    # a 6-hex (24-bit) nonce is now too short and must be rejected loudly
    import pytest
    with pytest.raises(ValueError, match="nonce must be 12 hex"):
        wrap_untrusted("PR_DIFF", "abc123", "body")
