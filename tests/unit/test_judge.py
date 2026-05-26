from types import SimpleNamespace

from bench.runner.judge import JudgeVerdict, usage_to_tokens


def test_judge_verdict_schema():
    v = JudgeVerdict(verdict="MATCH", reason="keywords align")
    assert v.verdict == "MATCH"


def test_usage_to_tokens_maps_sdk_fields():
    usage = SimpleNamespace(
        input_tokens=100,
        output_tokens=20,
        cache_read_input_tokens=40,
        cache_creation_input_tokens=10,
    )
    tu = usage_to_tokens(usage)
    assert tu.input == 100
    assert tu.output == 20
    assert tu.cache_read == 40
    assert tu.cache_write_5m == 0  # judge does no caching
    assert tu.cache_write_1h == 0
