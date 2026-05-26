import pytest
from pydantic import ValidationError

from bench.runner.models import GroundTruthFinding, NegativeAnchor


def _gt_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "file": "a.js",
        "lines": "10-20",
        "severity": "SERIOUS",
        "must_mention": ["CRLF"],
        "description": "CRLF injection via unsanitized header value",
    }
    base.update(overrides)
    return base


def test_minimal_valid() -> None:
    gt = GroundTruthFinding(**_gt_kwargs())  # type: ignore[arg-type]
    assert gt.cwe is None
    assert gt.mandatory is False


def test_must_mention_required_nonempty() -> None:
    with pytest.raises(ValidationError):
        GroundTruthFinding(**_gt_kwargs(must_mention=[]))  # type: ignore[arg-type]


def test_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        GroundTruthFinding(**_gt_kwargs(bogus=1))  # type: ignore[arg-type]


def test_description_required_nonempty() -> None:
    # description gives the judge real semantics (Track-3 P2) — must be present + non-empty
    with pytest.raises(ValidationError):
        GroundTruthFinding(file="a.js", lines="10", severity="SERIOUS", must_mention=["x"])
    with pytest.raises(ValidationError):
        GroundTruthFinding(**_gt_kwargs(description=""))  # type: ignore[arg-type]


def test_negative_anchor_minimal_valid() -> None:
    na = NegativeAnchor(file="a.ts", lines="40-42", why_benign="guarded eval behind a constant")
    assert na.file == "a.ts"
    assert na.lines == "40-42"


def test_negative_anchor_why_benign_required_nonempty() -> None:
    with pytest.raises(ValidationError):
        NegativeAnchor(file="a.ts", lines="40", why_benign="")


def test_negative_anchor_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        NegativeAnchor(file="a.ts", lines="40", why_benign="ok", bogus=1)
