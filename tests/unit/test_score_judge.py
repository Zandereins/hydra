"""score-judge CLI seam — pure gate/format/model/outage helpers + the outage guards.

The billed path (Anthropic() + make_judge) is exercised only by the integration test; here
we cover the offline-decidable behaviour: the accuracy gate, the human/JSON rendering, model
resolution precedence, and the central guarantee that every harness outage (no credential /
empty or unreadable gold-set / a fully-degraded auth-rejected run) maps to exit 2, never to a
quality regression (exit 1).
"""
from __future__ import annotations

import json
from dataclasses import asdict, replace

import pytest

from bench.runner import score_judge
from bench.runner.judge_eval import JudgeMetrics
from bench.runner.score_judge import (
    DEFAULT_JUDGE_MODEL,
    emit,
    format_human,
    gate_exit_code,
    has_anthropic_credential,
    is_total_judge_outage,
    resolve_model,
    run_score_judge,
)


def _metrics(accuracy: float, *, n: int = 40) -> JudgeMetrics:
    """Representative metrics; only `accuracy` drives the gate, the bias fields drive format."""
    return JudgeMetrics(
        n=n,
        accuracy=accuracy,
        true_match=18,
        true_no_match=17,
        false_match=2,
        false_no_match=3,
        false_match_rate=0.10,
        false_no_match_rate=0.15,
    )


# --- gate_exit_code: 0=pass / 1=regression, inclusive >= threshold, None never gates ---


def test_gate_pass_above_threshold() -> None:
    assert gate_exit_code(_metrics(0.90), 0.80) == 0


def test_gate_fail_below_threshold() -> None:
    assert gate_exit_code(_metrics(0.70), 0.80) == 1


def test_gate_inclusive_boundary() -> None:
    # accuracy == threshold passes (mirrors the integration `accuracy >= ACCURACY_FLOOR`)
    assert gate_exit_code(_metrics(0.80), 0.80) == 0


def test_gate_none_never_fires() -> None:
    assert gate_exit_code(_metrics(0.0), None) == 0


# --- format_human / emit: leniency<-false_match_rate, strictness<-false_no_match_rate ---


def test_human_maps_bias_axes_without_transposition() -> None:
    line = format_human(_metrics(0.875))
    assert "accuracy=0.875" in line
    assert "n=40" in line
    assert "leniency=0.10" in line  # <- false_match_rate
    assert "strictness=0.15" in line  # <- false_no_match_rate


def test_emit_json_is_exactly_asdict(capsys: pytest.CaptureFixture[str]) -> None:
    m = _metrics(0.875)
    emit(m, as_json=True)
    out = capsys.readouterr().out.strip()
    assert json.loads(out) == asdict(m)  # drift-proof: no hand-typed keys
    assert "\n" not in out  # single jq-parseable line


# --- resolve_model precedence: --model > $HYDRA_JUDGE_MODEL > haiku default ---


def test_model_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYDRA_JUDGE_MODEL", raising=False)
    assert resolve_model(None) == DEFAULT_JUDGE_MODEL


def test_model_env_over_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HYDRA_JUDGE_MODEL", "env-model")
    assert resolve_model(None) == "env-model"


def test_model_cli_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HYDRA_JUDGE_MODEL", "env-model")
    assert resolve_model("cli-model") == "cli-model"


# --- has_anthropic_credential: accept either env var the SDK reads ---


def test_credential_present_with_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert has_anthropic_credential() is True


def test_credential_present_with_auth_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok-x")  # SDK authenticates from this too
    assert has_anthropic_credential() is True


def test_credential_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert has_anthropic_credential() is False


# --- is_total_judge_outage: zero MATCH verdicts on a non-empty set = outage, not regression ---


def test_total_outage_when_no_match_verdicts() -> None:
    # invalid-key path: every pair 401s -> NO_MATCH -> tm=fm=0 on the 20/20 set -> acc 0.50
    m = replace(_metrics(0.50), true_match=0, false_match=0, true_no_match=20, false_no_match=20)
    assert is_total_judge_outage(m) is True


def test_not_outage_when_some_match_verdicts() -> None:
    assert is_total_judge_outage(_metrics(0.875)) is False  # tm=18, fm=2


def test_empty_metrics_is_not_total_outage() -> None:
    # n==0 is handled by the empty-gold-set guard (exit 2 there); the helper must not also
    # claim it, to keep the two outage sources distinct.
    m = replace(_metrics(0.0, n=0), true_match=0, false_match=0, true_no_match=0, false_no_match=0)
    assert is_total_judge_outage(m) is False


# --- run_score_judge outage routing: every infra failure -> exit 2, returned pre-billing ---


def test_missing_credential_is_outage_not_regression(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    # returns 2 BEFORE any client construction or billed call
    assert run_score_judge(model=None, check=0.80, as_json=False, yes=True) == 2


def test_missing_gold_set_is_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")

    def _raise() -> list[object]:
        raise FileNotFoundError("judge_gold.jsonl")

    monkeypatch.setattr(score_judge, "load_gold_set", _raise)
    # FileNotFoundError (an OSError) -> exit 2, returned before the billed path
    assert run_score_judge(model=None, check=0.80, as_json=False, yes=True) == 2


def test_empty_gold_set_is_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    monkeypatch.setattr(score_judge, "load_gold_set", list)  # returns []
    # empty set must not be scored as accuracy 0.0 -> exit 1; it is an outage -> exit 2
    assert run_score_judge(model=None, check=0.80, as_json=False, yes=True) == 2
