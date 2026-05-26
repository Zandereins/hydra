"""Guards against the anthropic SDK surface the judge depends on (0.45->0.96 drift)."""
import os

import pytest


def test_messages_parse_and_output_format_param_exist():
    import inspect

    from anthropic.resources.messages import Messages

    assert hasattr(Messages, "parse"), "judge requires client.messages.parse"
    params = inspect.signature(Messages.parse).parameters
    assert "output_format" in params
    assert "temperature" in params


def test_parsed_message_exposes_parsed_output():
    # judge.py reads msg.parsed_output to get the JudgeVerdict — guard that surface.
    from anthropic.types.parsed_message import ParsedMessage

    assert hasattr(ParsedMessage, "parsed_output")


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="no API key")
def test_live_parse_roundtrip():
    from anthropic import Anthropic

    from bench.runner.judge import JudgeVerdict

    client = Anthropic()
    msg = client.messages.parse(
        model="claude-haiku-4-5-20251001",
        max_tokens=64,
        temperature=0,
        messages=[{"role": "user", "content": "Reply MATCH."}],
        output_format=JudgeVerdict,
    )
    assert msg.parsed_output.verdict in ("MATCH", "NO_MATCH")
