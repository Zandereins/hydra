"""Bench ground-truth schema (spec Track-2 §3.1, RECONCILE-2)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from hydra.envelopes import IssueClass, Severity


class GroundTruthFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str
    lines: str  # "N" | "N-M" — same grammar as candidates (back-compat)
    severity: Severity
    must_mention: list[str] = Field(min_length=1)  # >=1 keyword must match (or judge adjudicates)
    # human-readable bug description — gives the judge real semantics (Track-3 P2)
    description: str = Field(min_length=1)
    cwe: str | None = None
    mandatory: bool = False
    issue_class: IssueClass = IssueClass.other


class NegativeAnchor(BaseModel):
    """A benign code location a thorough reviewer should NOT flag (Track-3 P2).

    A candidate finding overlapping a negative anchor (file + range) is counted as an
    explicit false positive — the distractor-resistance signal behind
    ``CaseScore.false_positive_rate``. Negative anchors must NOT overlap any
    ground-truth finding in the same case (enforced by the case-validation test), so a
    real match is never mis-counted as an FP.
    """

    model_config = ConfigDict(extra="forbid")

    file: str
    lines: str  # same grammar as GroundTruthFinding / candidates
    why_benign: str = Field(min_length=1)  # why this look-suspicious code is actually safe
