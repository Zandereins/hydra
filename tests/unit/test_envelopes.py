import json

from hydra.envelopes import (
    AdvisorFinding,
    Chain,
    GroundingStatus,
    IssueClass,
    Position,
    RunConfig,
    SeedReport,
    Severity,
    StructuralContext,
)


def test_run_config_round_trip() -> None:
    cfg = RunConfig(
        mode="deep",
        profile="quality",
        focus=None,
        allow_broken=False,
        tensions_only=False,
        resolved_models={"cassandra": "claude-opus-4-7"},
        run_nonce="abc123",
        config_hash="sha256:" + "0" * 64,
    )
    blob = cfg.model_dump_json()
    cfg2 = RunConfig.model_validate_json(blob)
    assert cfg == cfg2


def test_seed_report_byte_identical_serialization() -> None:
    sr = SeedReport(
        schema_version="2.0",
        generated_at="2026-04-17T14:30:00Z",
        run_nonce="abc123",
        tool_findings=[],
        echo_findings=[],
        navigator_findings=[],
        structural_context=StructuralContext(file_tree=[], boundaries=[], import_observations=[]),
        skipped_tools=[],
        warnings=[],
    )
    b1 = sr.canonical_json()
    b2 = sr.canonical_json()
    assert b1 == b2
    # sort_keys=True enforced
    parsed = json.loads(b1)
    assert list(parsed.keys()) == sorted(parsed.keys())


def test_advisor_finding_has_required_fields() -> None:
    f = AdvisorFinding(
        id="C-1",
        title="Race in refresh",
        severity=Severity.SERIOUS,
        evidence="VERIFIED",
        position=Position.CONCERN,
        file="auth.ts",
        lines="47-62",
        issue_class=IssueClass.race_condition,
        chain=Chain(
            premise="single concurrent request",
            execution_trace="req1 → refreshToken() → req2 → refreshToken()",
            conclusion="second overwrites first",
        ),
        extends_seed=["T-SEM-3"],
        challenges_seed=[],
        novel=False,
    )
    assert f.grounding == GroundingStatus.UNKNOWN  # default pre-grounding
    assert f.is_tension is False


def test_run_config_rejects_bad_nonce() -> None:
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="run_nonce"):
        RunConfig(
            mode="deep", profile="quality", focus=None,
            allow_broken=False, tensions_only=False,
            resolved_models={},
            run_nonce="ZZZZZZ",  # not hex
            config_hash="sha256:" + "0" * 64,
        )


def test_run_config_rejects_bad_config_hash() -> None:
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="config_hash"):
        RunConfig(
            mode="deep", profile="quality", focus=None,
            allow_broken=False, tensions_only=False,
            resolved_models={},
            run_nonce="abcdef",
            config_hash="not-a-hash",
        )
