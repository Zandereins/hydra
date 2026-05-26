import pytest
from pydantic import ValidationError

from bench.runner.models import GroundTruthFinding


def test_minimal_valid() -> None:
    gt = GroundTruthFinding(file="a.js", lines="10-20", severity="SERIOUS", must_mention=["CRLF"])
    assert gt.cwe is None
    assert gt.mandatory is False


def test_must_mention_required_nonempty() -> None:
    with pytest.raises(ValidationError):
        GroundTruthFinding(file="a.js", lines="10", severity="SERIOUS", must_mention=[])


def test_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        GroundTruthFinding(file="a.js", lines="10", severity="SERIOUS", must_mention=["x"], bogus=1)
