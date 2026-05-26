from pathlib import Path

from hydra.envelopes import AdvisorFinding, Chain, GroundingStatus, Position, Severity
from hydra.grounding import (
    CITATION_THRESHOLD,
    GroundingSummary,
    _parse_line_range,
    count_present,
    demote,
    extract_salient_tokens,
    ground_finding,
    read_range,
    summarize,
)

# ---------------------------------------------------------------------------
# Task 1: line-range reader
# ---------------------------------------------------------------------------


def test_parse_single_and_range() -> None:
    assert _parse_line_range("142") == (142, 142)
    assert _parse_line_range("142-158") == (142, 158)


def test_parse_invalid_returns_none() -> None:
    assert _parse_line_range("") is None
    assert _parse_line_range("abc") is None
    assert _parse_line_range("3-1") is None  # reversed


def test_read_range_returns_joined_lines(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("a\nb\nc\nd\ne\n")
    assert read_range(f, "2-4") == "b\nc\nd"


def test_read_range_out_of_bounds_returns_none(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("a\nb\n")
    assert read_range(f, "5-6") is None


def test_read_range_dos_cap(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("\n".join(str(i) for i in range(10_000)))
    # a malicious huge range is capped, never returns the whole file
    out = read_range(f, "1-9999999", max_lines=50)
    assert out is not None
    assert out.count("\n") <= 49


def test_read_range_caps_pathological_single_line(tmp_path: Path) -> None:
    f = tmp_path / "min.js"
    f.write_text("x" * 5_000_000)  # one 5MB line, no newline — bypasses a line-only cap
    out = read_range(f, "1", max_lines=200, max_line_bytes=4096)
    assert out is not None
    assert len(out) <= 4096  # byte cap applied, not the whole 5MB line


def test_read_range_trailing_newline_has_no_phantom_line(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("a\nb\n")  # 2 real lines; the trailing \n must not create a phantom line 3
    assert read_range(f, "2") == "b"
    assert read_range(f, "3") is None


# ---------------------------------------------------------------------------
# Task 2: salient-token extraction + presence count
# ---------------------------------------------------------------------------


def _finding(**kw: object) -> AdvisorFinding:
    base: dict[str, object] = dict(
        id="f1",
        title="CRLF injection in setHeader",
        severity=Severity.SERIOUS,
        evidence="VERIFIED",
        position=Position.CONCERN,
        file="lib/core/AxiosHeaders.js",
        lines="142-158",
        chain=Chain(
            premise="user value flows into setHeader",
            execution_trace="",
            conclusion="enables header injection",
        ),
    )
    base.update(kw)
    return AdvisorFinding(**base)


def test_extract_salient_tokens_from_title_and_chain() -> None:
    tokens = extract_salient_tokens(_finding())
    assert "CRLF" in tokens
    assert "setHeader" in tokens
    assert "injection" in tokens
    assert all(len(t) >= 3 for t in tokens)
    assert len(tokens) <= 8


def test_count_present_is_case_insensitive() -> None:
    assert count_present(["setHeader", "CRLF"], "function setHeader(){ // crlf } ") == 2
    assert count_present(["nonexistent"], "abc") == 0


# ---------------------------------------------------------------------------
# Task 3: severity-demotion ladder
# ---------------------------------------------------------------------------


def test_demote_drops_one_rung() -> None:
    assert demote(Severity.CATASTROPHIC) == Severity.SERIOUS
    assert demote(Severity.SERIOUS) == Severity.MODERATE
    assert demote(Severity.MODERATE) == Severity.MINOR
    assert demote(Severity.MINOR) == Severity.TRIVIAL


def test_demote_floor_is_trivial() -> None:
    assert demote(Severity.TRIVIAL) == Severity.TRIVIAL


# ---------------------------------------------------------------------------
# Task 4: ground_finding — all status branches
# ---------------------------------------------------------------------------

# CITATION_THRESHOLD imported to document the public API; validated indirectly
# by test_citation_present_when_tokens_match + test_token_mismatch_demotes.
_THRESHOLD = CITATION_THRESHOLD


def test_safety_position_not_applicable(tmp_path: Path) -> None:
    f = _finding(position=Position.APPROVE)
    ground_finding(f, tmp_path)
    assert f.grounding == GroundingStatus.NOT_APPLICABLE


def test_trivial_severity_not_applicable(tmp_path: Path) -> None:
    f = _finding(severity=Severity.TRIVIAL)
    ground_finding(f, tmp_path)
    assert f.grounding == GroundingStatus.NOT_APPLICABLE


def test_no_citation_demotes(tmp_path: Path) -> None:
    f = _finding(file=None, lines=None, severity=Severity.SERIOUS)
    ground_finding(f, tmp_path)
    assert f.grounding == GroundingStatus.NO_CITATION
    assert f.severity == Severity.MODERATE  # demoted one rung


def test_path_escape_flagged(tmp_path: Path) -> None:
    f = _finding(file="../../etc/passwd", lines="1-2")
    ground_finding(f, tmp_path)
    assert f.grounding == GroundingStatus.PATH_ESCAPE


def test_file_missing_demotes(tmp_path: Path) -> None:
    f = _finding(file="nope.js", lines="1-2", severity=Severity.SERIOUS)
    ground_finding(f, tmp_path)
    assert f.grounding == GroundingStatus.FILE_MISSING
    assert f.severity == Severity.MODERATE


def test_range_missing_demotes(tmp_path: Path) -> None:
    (tmp_path / "lib").mkdir(parents=True)
    (tmp_path / "lib" / "core").mkdir()
    (tmp_path / "lib" / "core" / "AxiosHeaders.js").write_text("a\nb\n")
    f = _finding(lines="50-60", severity=Severity.SERIOUS)
    ground_finding(f, tmp_path)
    assert f.grounding == GroundingStatus.RANGE_MISSING
    assert f.severity == Severity.MODERATE


def test_citation_present_when_tokens_match(tmp_path: Path) -> None:
    p = tmp_path / "lib" / "core"
    p.mkdir(parents=True)
    content = "\n" * 141 + "setHeader(name){ /* CRLF injection */ }\n" * 17
    (p / "AxiosHeaders.js").write_text(content)
    f = _finding(severity=Severity.SERIOUS)
    ground_finding(f, tmp_path)
    assert f.grounding == GroundingStatus.CITATION_PRESENT
    assert f.severity == Severity.SERIOUS  # not demoted


def test_token_mismatch_demotes(tmp_path: Path) -> None:
    p = tmp_path / "lib" / "core"
    p.mkdir(parents=True)
    (p / "AxiosHeaders.js").write_text("\n" * 141 + "unrelated boring code\n" * 17)
    f = _finding(severity=Severity.SERIOUS)
    ground_finding(f, tmp_path)
    assert f.grounding == GroundingStatus.TOKEN_MISMATCH
    assert f.severity == Severity.MODERATE


# ---------------------------------------------------------------------------
# Task 5: Grounding Summary
# ---------------------------------------------------------------------------


def test_summarize_counts_and_renders() -> None:
    f1 = _finding()
    f1.grounding = GroundingStatus.CITATION_PRESENT
    f2 = _finding()
    f2.grounding = GroundingStatus.NOT_APPLICABLE
    f3 = _finding()
    f3.grounding = GroundingStatus.TOKEN_MISMATCH
    f4 = _finding()
    f4.grounding = GroundingStatus.PATH_ESCAPE
    findings = [f1, f2, f3, f4]

    summary = summarize(findings)
    assert isinstance(summary, GroundingSummary)
    assert summary.total == 4
    assert summary.citation_present == 1
    assert summary.not_applicable == 1
    assert summary.demoted == 1  # TOKEN_MISMATCH
    assert summary.dropped == 1  # PATH_ESCAPE
    assert summary.demoted_breakdown["TOKEN_MISMATCH"] == 1
    rendered = summary.render()
    assert "## Grounding Summary" in rendered
    assert "CITATION_PRESENT: 1" in rendered
    assert "Auto-demoted: 1 (1 TOKEN_MISMATCH)" in rendered  # per-status breakdown (spec §2.5)


def test_read_range_comma_separated_span(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("\n".join(str(i) for i in range(1, 31)))  # lines "1".."30"
    # "15,21-22" spans min=15..max=22 -> lines 15..22 (values 15..22)
    out = read_range(f, "15,21-22")
    assert out is not None
    assert out.splitlines()[0] == "15"
    assert out.splitlines()[-1] == "22"


def test_path_escape_beats_file_missing(tmp_path: Path) -> None:
    # A path that BOTH escapes the repo AND does not exist must report PATH_ESCAPE,
    # not FILE_MISSING (the whole point of escape-first / must_exist=False).
    f = _finding(file="../../nonexistent-xyz-12345.js", lines="1-2", severity=Severity.SERIOUS)
    ground_finding(f, tmp_path)
    assert f.grounding == GroundingStatus.PATH_ESCAPE
    assert f.severity == Severity.SERIOUS  # PATH_ESCAPE drops to panel, does NOT demote


def test_no_citation_when_only_lines_missing(tmp_path: Path) -> None:
    f = _finding(file="x.js", lines=None, severity=Severity.SERIOUS)
    ground_finding(f, tmp_path)
    assert f.grounding == GroundingStatus.NO_CITATION
    assert f.severity == Severity.MODERATE  # demoted one rung


def test_read_range_multiline_byte_budget(tmp_path: Path) -> None:
    # When early near-cap lines exhaust the byte budget, later in-range lines drop out
    # (documented behavior) — but each returned line is still truncated to max_line_bytes.
    f = tmp_path / "x.py"
    f.write_text("\n".join("a" * 4000 for _ in range(10)))
    out = read_range(f, "1-10", max_lines=3, max_line_bytes=4096)
    assert out is not None
    for line in out.splitlines():
        assert len(line) <= 4096
