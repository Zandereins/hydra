import re

from hydra.run_nonce import UNTRUSTED_RE, mint_nonce, wrap_untrusted


def test_mint_nonce_format() -> None:
    nonce = mint_nonce()
    assert re.fullmatch(r"[0-9a-f]{6}", nonce)


def test_mint_nonce_unique_across_calls() -> None:
    # 48-bit nonce — collisions are negligible for any realistic sample
    samples = {mint_nonce() for _ in range(1000)}
    assert len(samples) == 1000


def test_wrap_untrusted_emits_correct_tags() -> None:
    out = wrap_untrusted("PR_DIFF", "abc123", "diff --git a/x b/x\n")
    assert out.startswith("<<UNTRUSTED_PR_DIFF_abc123>>")
    assert out.endswith("<<END_UNTRUSTED_PR_DIFF_abc123>>")


def test_untrusted_re_matches_wrapped_block() -> None:
    wrapped = wrap_untrusted("ADVISOR_OUTPUT_cassandra", "abc123", "finding")
    assert UNTRUSTED_RE.search(wrapped) is not None
