import json

import pytest

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
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="config_hash"):
        RunConfig(
            mode="deep", profile="quality", focus=None,
            allow_broken=False, tensions_only=False,
            resolved_models={},
            run_nonce="abcdef",
            config_hash="not-a-hash",
        )


def _make_seed_report(generated_at: str = "2026-01-01T00:00:00Z") -> SeedReport:
    return SeedReport(
        schema_version="2.0",
        generated_at=generated_at,
        run_nonce="abcdef",
        tool_findings=[],
        echo_findings=[],
        navigator_findings=[],
        structural_context=StructuralContext(),
        skipped_tools=[],
        warnings=[],
    )


@pytest.mark.xfail(
    strict=True,
    reason="A2-F9: generated_at currently inside canonical_json — fix in next commit",
)
def test_canonical_json_byte_stable_across_runs_with_different_timestamps() -> None:
    # Spec §4.3.1 L210: "No timestamps / run_ids inside cached blocks; put
    # them in uncached tail." Two SeedReports with identical logical content
    # but different generated_at MUST produce identical canonical bytes,
    # otherwise BP4 cache hit-rate goes to 0% (release-blocker per spec L216).
    sr_old = _make_seed_report(generated_at="2026-01-01T00:00:00Z")
    sr_new = _make_seed_report(generated_at="2099-12-31T23:59:59Z")
    assert sr_old.canonical_json() == sr_new.canonical_json(), (
        "canonical_json must not include generated_at — see A2-F9 finding"
    )


def test_canonical_json_keys_sorted_under_kwargs_reorder() -> None:
    # R3 thought-experiment: a patch silently dropping sort_keys=True would
    # pass every existing test if dict insertion order happens to match
    # alphabetical. Construct with deliberately reversed kwarg order to
    # break that coincidence and force the sort.
    sr = SeedReport(
        warnings=[],
        skipped_tools=[],
        structural_context=StructuralContext(),
        navigator_findings=[],
        echo_findings=[],
        tool_findings=[],
        run_nonce="abcdef",
        generated_at="2026-01-01T00:00:00Z",
        schema_version="2.0",
    )
    parsed = json.loads(sr.canonical_json())
    keys = list(parsed.keys())
    assert keys == sorted(keys), f"canonical_json keys not sorted: {keys}"


def test_canonical_json_idempotent_on_repeated_call() -> None:
    # Sanity check that two calls on the same object return identical bytes.
    # If this ever breaks, the bug is in `model_dump(mode='json')`
    # nondeterminism, not in the F9 timestamp issue.
    sr = _make_seed_report()
    assert sr.canonical_json() == sr.canonical_json()
