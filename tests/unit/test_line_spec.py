"""Shared line-spec parser — the single source of truth for citation ranges.

Previously two divergent copies existed (hydra.grounding._parse_line_range collapsed to
(min,max) and failed the whole spec on a bad part; bench.runner.scoring._parse_ranges
kept sub-spans and skipped bad ones, raising on non-ints). This module unifies the grammar
with one fail-soft semantic: invalid sub-spans (non-integer, zero/negative, reversed) are
dropped; the valid spans are returned."""
from __future__ import annotations

from hydra.line_spec import MAX_LINE_SPANS, parse_line_spans


def test_single_line() -> None:
    assert parse_line_spans("142") == [(142, 142)]


def test_range() -> None:
    assert parse_line_spans("142-158") == [(142, 158)]


def test_comma_multi_span_preserves_subspans() -> None:
    assert parse_line_spans("15,21-22") == [(15, 15), (21, 22)]


def test_empty_and_blank_parts_skipped() -> None:
    assert parse_line_spans("") == []
    assert parse_line_spans("1, ,3") == [(1, 1), (3, 3)]


def test_non_integer_subspans_dropped_fail_soft() -> None:
    assert parse_line_spans("abc") == []
    assert parse_line_spans("abc,142") == [(142, 142)]


def test_reversed_and_zero_subspans_dropped() -> None:
    assert parse_line_spans("3-1") == []  # reversed
    assert parse_line_spans("0") == []  # zero (1-indexed)
    assert parse_line_spans("3-1,5-6") == [(5, 6)]  # drop only the bad span
    assert parse_line_spans("0,4-5") == [(4, 5)]


def test_span_count_is_capped() -> None:
    spec = ",".join(str(i) for i in range(1, 500))  # 499 comma-spans
    assert len(parse_line_spans(spec)) == MAX_LINE_SPANS
