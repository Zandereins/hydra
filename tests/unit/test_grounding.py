from pathlib import Path

from hydra.grounding import _parse_line_range, read_range


def test_parse_single_and_range():
    assert _parse_line_range("142") == (142, 142)
    assert _parse_line_range("142-158") == (142, 158)


def test_parse_invalid_returns_none():
    assert _parse_line_range("") is None
    assert _parse_line_range("abc") is None
    assert _parse_line_range("3-1") is None  # reversed


def test_read_range_returns_joined_lines(tmp_path: Path):
    f = tmp_path / "x.py"
    f.write_text("a\nb\nc\nd\ne\n")
    assert read_range(f, "2-4") == "b\nc\nd"


def test_read_range_out_of_bounds_returns_none(tmp_path: Path):
    f = tmp_path / "x.py"
    f.write_text("a\nb\n")
    assert read_range(f, "5-6") is None


def test_read_range_dos_cap(tmp_path: Path):
    f = tmp_path / "x.py"
    f.write_text("\n".join(str(i) for i in range(10_000)))
    # a malicious huge range is capped, never returns the whole file
    out = read_range(f, "1-9999999", max_lines=50)
    assert out is not None
    assert out.count("\n") <= 49


from hydra.envelopes import AdvisorFinding, Chain, GroundingStatus, Position, Severity
from hydra.grounding import count_present, extract_salient_tokens


def _finding(**kw) -> AdvisorFinding:  # type: ignore[no-untyped-def]
    base = dict(
        id="f1", title="CRLF injection in setHeader",
        severity=Severity.SERIOUS, evidence="VERIFIED", position=Position.CONCERN,
        file="lib/core/AxiosHeaders.js", lines="142-158",
        chain=Chain(premise="user value flows into setHeader", execution_trace="", conclusion="enables header injection"),
    )
    base.update(kw)
    return AdvisorFinding(**base)


def test_extract_salient_tokens_from_title_and_chain():
    tokens = extract_salient_tokens(_finding())
    assert "CRLF" in tokens
    assert "setHeader" in tokens
    assert "injection" in tokens
    assert all(len(t) >= 3 for t in tokens)
    assert len(tokens) <= 8


def test_count_present_is_case_insensitive():
    assert count_present(["setHeader", "CRLF"], "function setHeader(){ // crlf } ") == 2
    assert count_present(["nonexistent"], "abc") == 0


from hydra.grounding import demote


def test_demote_drops_one_rung():
    assert demote(Severity.CATASTROPHIC) == Severity.SERIOUS
    assert demote(Severity.SERIOUS) == Severity.MODERATE
    assert demote(Severity.MODERATE) == Severity.MINOR
    assert demote(Severity.MINOR) == Severity.TRIVIAL


def test_demote_floor_is_trivial():
    assert demote(Severity.TRIVIAL) == Severity.TRIVIAL


from hydra.grounding import CITATION_THRESHOLD, ground_finding


def test_safety_position_not_applicable(tmp_path):  # type: ignore[no-untyped-def]
    f = _finding(position=Position.APPROVE)
    ground_finding(f, tmp_path)
    assert f.grounding == GroundingStatus.NOT_APPLICABLE


def test_trivial_severity_not_applicable(tmp_path):  # type: ignore[no-untyped-def]
    f = _finding(severity=Severity.TRIVIAL)
    ground_finding(f, tmp_path)
    assert f.grounding == GroundingStatus.NOT_APPLICABLE


def test_no_citation_demotes(tmp_path):  # type: ignore[no-untyped-def]
    f = _finding(file=None, lines=None, severity=Severity.SERIOUS)
    ground_finding(f, tmp_path)
    assert f.grounding == GroundingStatus.NO_CITATION
    assert f.severity == Severity.MODERATE  # demoted one rung


def test_path_escape_flagged(tmp_path):  # type: ignore[no-untyped-def]
    f = _finding(file="../../etc/passwd", lines="1-2")
    ground_finding(f, tmp_path)
    assert f.grounding == GroundingStatus.PATH_ESCAPE


def test_file_missing_demotes(tmp_path):  # type: ignore[no-untyped-def]
    f = _finding(file="nope.js", lines="1-2", severity=Severity.SERIOUS)
    ground_finding(f, tmp_path)
    assert f.grounding == GroundingStatus.FILE_MISSING
    assert f.severity == Severity.MODERATE


def test_range_missing_demotes(tmp_path):  # type: ignore[no-untyped-def]
    (tmp_path / "lib").mkdir(parents=True)
    (tmp_path / "lib" / "core").mkdir()
    (tmp_path / "lib" / "core" / "AxiosHeaders.js").write_text("a\nb\n")
    f = _finding(lines="50-60", severity=Severity.SERIOUS)
    ground_finding(f, tmp_path)
    assert f.grounding == GroundingStatus.RANGE_MISSING
    assert f.severity == Severity.MODERATE


def test_citation_present_when_tokens_match(tmp_path):  # type: ignore[no-untyped-def]
    p = tmp_path / "lib" / "core"
    p.mkdir(parents=True)
    (p / "AxiosHeaders.js").write_text("\n" * 141 + "setHeader(name){ /* CRLF injection */ }\n" * 17)
    f = _finding(severity=Severity.SERIOUS)
    ground_finding(f, tmp_path)
    assert f.grounding == GroundingStatus.CITATION_PRESENT
    assert f.severity == Severity.SERIOUS  # not demoted


def test_token_mismatch_demotes(tmp_path):  # type: ignore[no-untyped-def]
    p = tmp_path / "lib" / "core"
    p.mkdir(parents=True)
    (p / "AxiosHeaders.js").write_text("\n" * 141 + "unrelated boring code\n" * 17)
    f = _finding(severity=Severity.SERIOUS)
    ground_finding(f, tmp_path)
    assert f.grounding == GroundingStatus.TOKEN_MISMATCH
    assert f.severity == Severity.MODERATE


from hydra.grounding import GroundingSummary, summarize


def test_summarize_counts_and_renders():
    findings = [
        _finding(),  # will be UNKNOWN until grounded; set explicitly below
    ]
    findings[0].grounding = GroundingStatus.CITATION_PRESENT
    f2 = _finding(); f2.grounding = GroundingStatus.NOT_APPLICABLE
    f3 = _finding(); f3.grounding = GroundingStatus.TOKEN_MISMATCH
    f4 = _finding(); f4.grounding = GroundingStatus.PATH_ESCAPE
    findings += [f2, f3, f4]

    summary = summarize(findings)
    assert isinstance(summary, GroundingSummary)
    assert summary.total == 4
    assert summary.citation_present == 1
    assert summary.not_applicable == 1
    assert summary.demoted == 1  # TOKEN_MISMATCH
    assert summary.dropped == 1  # PATH_ESCAPE
    rendered = summary.render()
    assert "## Grounding Summary" in rendered
    assert "CITATION_PRESENT: 1" in rendered
