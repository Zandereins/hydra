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


def test_judge_prompt_excludes_must_mention_keeps_description() -> None:
    """The judge adjudicates the keyword-FAIL subset; leaking must_mention into its prompt
    hands it the lexical rubric and lets a persuasive-wrong-with-keywords candidate fool the
    semantic judgment. The prompt must carry the semantic `description`, never the keywords."""
    client = _FakeClient("NO_MATCH")
    judge = make_judge(client=client, model="m")
    gt: dict[str, object] = {
        "file": "a.js",
        "lines": "1",
        "description": "semantic root cause SENTINELDESC",
        "must_mention": ["LEAKYKEYWORD"],
    }
    judge(gt, {"title": "x"})
    prompt = client.calls[0]["messages"][0]["content"]
    assert "SENTINELDESC" in prompt  # semantic ground truth is given
    assert "LEAKYKEYWORD" not in prompt  # lexical rubric is NOT leaked


def test_judge_disabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JUDGE_ENABLED", "0")
    assert resolve_judge(client=_FakeClient("MATCH"), model="m") is None


# --- transient-error retry (P4 follow-up: the one gold-set miss was an API 529) ---

_GT: dict[str, object] = {"file": "a", "lines": "1", "must_mention": ["x"], "description": "d"}
_CAND: dict[str, object] = {"title": "t"}


def _client_raising(exc_factory: object, *, succeed_after: int = 10**9) -> SimpleNamespace:
    """A client whose parse() raises exc_factory() until the `succeed_after`-th call."""
    calls: list[int] = []

    def _parse(**_kw: object) -> SimpleNamespace:
        calls.append(1)
        if len(calls) >= succeed_after:
            return SimpleNamespace(parsed_output=JudgeVerdict(verdict="MATCH", reason="x"))  # type: ignore[arg-type]
        raise exc_factory()  # type: ignore[operator]

    ns = SimpleNamespace(messages=SimpleNamespace(parse=_parse))
    ns.calls = calls  # type: ignore[attr-defined]
    return ns


class _Overloaded(Exception):
    status_code = 529


class _Unauthorized(Exception):
    status_code = 401


def test_judge_retries_transient_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    import bench.runner.judge as judge_mod

    monkeypatch.setattr(judge_mod.time, "sleep", lambda *_a: None)
    client = _client_raising(_Overloaded, succeed_after=3)  # fail twice, then succeed
    assert make_judge(client=client, model="m")(_GT, _CAND) is True
    assert len(client.calls) == 3  # 2 transient retries + success — not degraded


def test_judge_does_not_retry_permanent_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import bench.runner.judge as judge_mod

    monkeypatch.setattr(judge_mod.time, "sleep", lambda *_a: None)
    client = _client_raising(_Unauthorized)  # 401 -> permanent
    assert make_judge(client=client, model="m")(_GT, _CAND) is False
    assert len(client.calls) == 1  # degrade immediately, no retry


def test_judge_degrades_after_exhausting_transient_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    import bench.runner.judge as judge_mod

    monkeypatch.setattr(judge_mod.time, "sleep", lambda *_a: None)
    client = _client_raising(_Overloaded)  # always overloaded
    assert make_judge(client=client, model="m")(_GT, _CAND) is False
    assert len(client.calls) == judge_mod.JUDGE_MAX_RETRIES + 1  # initial try + N retries
