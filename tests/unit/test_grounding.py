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
