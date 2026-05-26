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
    cwe: str | None = None
    mandatory: bool = False
    issue_class: IssueClass = IssueClass.other
