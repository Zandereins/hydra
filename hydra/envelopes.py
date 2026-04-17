"""Dataclasses for inter-phase envelopes (§4.4 of spec)."""
from __future__ import annotations

import enum
import json
from typing import Any, Literal

from pydantic import BaseModel, Field


class Severity(enum.StrEnum):
    CATASTROPHIC = "CATASTROPHIC"
    SERIOUS = "SERIOUS"
    MODERATE = "MODERATE"
    MINOR = "MINOR"
    TRIVIAL = "TRIVIAL"


class Position(enum.StrEnum):
    APPROVE = "APPROVE"
    CONCERN = "CONCERN"
    REJECT = "REJECT"


class GroundingStatus(enum.StrEnum):
    UNKNOWN = "UNKNOWN"
    CITATION_PRESENT = "CITATION_PRESENT"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NO_CITATION = "NO_CITATION"
    FILE_MISSING = "FILE_MISSING"
    RANGE_MISSING = "RANGE_MISSING"
    TOKEN_MISMATCH = "TOKEN_MISMATCH"
    PATH_ESCAPE = "PATH_ESCAPE"


class IssueClass(enum.StrEnum):
    race_condition = "race_condition"
    deadlock = "deadlock"
    null_deref = "null_deref"
    buffer_overflow = "buffer_overflow"
    path_traversal = "path_traversal"
    command_injection = "command_injection"
    sql_injection = "sql_injection"
    xss = "xss"
    xxe = "xxe"
    csrf = "csrf"
    auth_bypass = "auth_bypass"
    session_fixation = "session_fixation"
    crypto_misuse = "crypto_misuse"
    secret_exposure = "secret_exposure"
    logic_error = "logic_error"
    off_by_one = "off_by_one"
    type_confusion = "type_confusion"
    resource_leak = "resource_leak"
    performance_degradation = "performance_degradation"
    api_break = "api_break"
    scope_creep = "scope_creep"
    phantom_helper = "phantom_helper"
    over_engineering = "over_engineering"
    fake_tdd = "fake_tdd"
    drift = "drift"
    comment_bloat = "comment_bloat"
    defensive_theatre = "defensive_theatre"
    readability = "readability"
    architectural_boundary = "architectural_boundary"
    dependency_vulnerability = "dependency_vulnerability"
    test_quality = "test_quality"
    other = "other"

    @classmethod
    def normalize(cls, value: str) -> IssueClass:
        try:
            return cls(value)
        except ValueError:
            return cls.other


class Chain(BaseModel):
    premise: str = ""
    execution_trace: str = ""
    conclusion: str = ""


class ToolFinding(BaseModel):
    id: str
    source: Literal["semgrep", "osv", "lang_checker"]
    rule_id: str = ""
    file: str | None = None
    lines: str | None = None
    severity: Severity = Severity.MODERATE
    message: str = Field("", max_length=500)


class AdvisorFinding(BaseModel):
    id: str
    title: str
    severity: Severity
    evidence: Literal["VERIFIED", "HYPOTHESIS_HIGH", "HYPOTHESIS_MEDIUM", "HYPOTHESIS_LOW"]
    position: Position
    file: str | None = None
    lines: str | None = None
    issue_class: IssueClass = IssueClass.other
    chain: Chain
    extends_seed: list[str] = Field(default_factory=list)
    challenges_seed: list[str] = Field(default_factory=list)
    novel: bool = False
    grounding: GroundingStatus = GroundingStatus.UNKNOWN
    is_tension: bool = False
    check_type: str | None = None  # Echo-specific
    pr_desc_quote: str | None = None  # Echo-specific


class StructuralContext(BaseModel):
    file_tree: list[str] = Field(default_factory=list)
    boundaries: list[dict[str, Any]] = Field(default_factory=list)
    import_observations: list[dict[str, Any]] = Field(default_factory=list)


class SeedReport(BaseModel):
    schema_version: Literal["2.0"] = "2.0"
    generated_at: str
    run_nonce: str = Field(pattern=r"^[0-9a-f]{6}$")
    tool_findings: list[ToolFinding] = Field(default_factory=list)
    echo_findings: list[AdvisorFinding] = Field(default_factory=list)
    navigator_findings: list[AdvisorFinding] = Field(default_factory=list)
    structural_context: StructuralContext = Field(default_factory=StructuralContext)
    skipped_tools: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def canonical_json(self) -> bytes:
        """Byte-identical JSON for cache-hygiene (BP4)."""
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")


class RunConfig(BaseModel):
    mode: Literal["standard", "deep"]
    profile: Literal["quality", "balanced", "budget"]
    focus: Literal["security", "perf", "readability", "architecture", "reliability"] | None
    allow_broken: bool
    tensions_only: bool
    resolved_models: dict[str, str]
    run_nonce: str = Field(pattern=r"^[0-9a-f]{6}$")
    config_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class GroundedFindings(BaseModel):
    findings: list[AdvisorFinding]
    degradation_panel: list[dict[str, Any]] = Field(default_factory=list)
    grounding_summary: dict[str, int] = Field(default_factory=dict)


class ChairmanInput(BaseModel):
    findings: list[AdvisorFinding]
    tensions: list[dict[str, Any]]
    degradation_panel: list[dict[str, Any]]
    seed_report_summary: dict[str, Any]
    run_config: RunConfig


class ChairmanOutput(BaseModel):
    verdict: Literal["APPROVE", "REQUEST_CHANGES", "CONCERN"]
    confidence: int = Field(ge=0, le=100)
    top_actions: list[dict[str, Any]]
    tensions_section: str = ""
    grounding_summary: str = ""
    suspicious_verdict_banner: str | None = None
