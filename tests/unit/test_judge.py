from types import SimpleNamespace

import pytest

from bench.runner.judge import JudgeVerdict, make_judge, resolve_judge


def test_judge_verdict_schema():
    v = JudgeVerdict(verdict="MATCH", reason="keywords align")
    assert v.verdict == "MATCH"


class _FakeClient:
    def __init__(self, verdict: str) -> None:
        self._verdict = verdict
        self.calls: list[dict[str, object]] = []
        self.messages = SimpleNamespace(parse=self._parse)

    def _parse(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            parsed_output=JudgeVerdict(verdict=self._verdict, reason="x"),  # type: ignore[arg-type]
            usage=SimpleNamespace(
                input_tokens=10,
                output_tokens=2,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
        )


def test_make_judge_returns_bool_and_calls_parse() -> None:
    client = _FakeClient("MATCH")
    judge = make_judge(client=client, model="claude-opus-4-7")
    gt: dict[str, object] = {"file": "a.js", "lines": "1", "must_mention": ["CRLF"]}
    cand: dict[str, object] = {"file": "a.js", "lines": "1", "title": "different words"}
    assert judge(gt, cand) is True
    assert len(client.calls) == 1
    assert client.calls[0]["temperature"] == 0
    assert client.calls[0]["output_format"] is JudgeVerdict


def test_make_judge_no_match() -> None:
    judge = make_judge(client=_FakeClient("NO_MATCH"), model="claude-opus-4-7")
    assert (
        judge(
            {"file": "a", "lines": "1", "must_mention": ["x"]},
            {"file": "a", "lines": "1", "title": "y"},
        )
        is False
    )


def test_judge_disabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JUDGE_ENABLED", "0")
    assert resolve_judge(client=_FakeClient("MATCH"), model="m") is None
