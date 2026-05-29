from bench.runner.scoring import RANGE_TOL, score_case


def test_exact_match_full_recall() -> None:
    gt = [{
        "file": "src/a.ts",
        "lines": "14-28",
        "severity": "SERIOUS",
        "issue_class": "auth_bypass",
        "mandatory": True,
        "must_mention": ["Authorization", "forwarded"],
    }]
    candidates: list[dict[str, object]] = [{
        "title": "Authorization header forwarded without check",
        "file": "src/a.ts",
        "lines": "14-28",
        "severity": "SERIOUS",
        "issue_class": "auth_bypass",
        "position": "REJECT",
    }]
    result = score_case(gt, candidates)
    assert result.recall == 1.0
    assert result.precision == 1.0
    assert result.f1 == 1.0


def test_missing_mandatory_zero_recall() -> None:
    gt = [{
        "file": "a.ts",
        "lines": "1-1",
        "severity": "SERIOUS",
        "issue_class": "auth_bypass",
        "mandatory": True,
        "must_mention": ["auth"],
    }]
    result = score_case(gt, [])
    assert result.recall == 0.0
    assert result.critical_recall == 0.0


def test_noise_drops_precision() -> None:
    gt = [{
        "file": "a.ts",
        "lines": "1-1",
        "severity": "SERIOUS",
        "issue_class": "auth_bypass",
        "mandatory": True,
        "must_mention": ["auth"],
    }]
    candidates: list[dict[str, object]] = [
        {"title": "auth bypass", "file": "a.ts", "lines": "1-1",
         "severity": "SERIOUS", "issue_class": "auth_bypass"},
        {"title": "irrelevant", "file": "b.ts", "lines": "5-5",
         "severity": "MINOR", "issue_class": "other"},
    ]
    result = score_case(gt, candidates)
    assert result.recall == 1.0
    assert result.precision == 0.5
    assert 0.6 < result.f1 < 0.7


def test_range_overlap_still_matches() -> None:
    gt = [{
        "file": "a.ts",
        "lines": "14-28",
        "severity": "SERIOUS",
        "issue_class": "auth_bypass",
        "mandatory": True,
        "must_mention": ["auth"],
    }]
    candidates: list[dict[str, object]] = [{
        "title": "auth bypass at line 20",
        "file": "a.ts",
        "lines": "20-32",
        "severity": "SERIOUS",
        "issue_class": "auth_bypass",
        "position": "CONCERN",
    }]
    result = score_case(gt, candidates)
    assert result.recall == 1.0


# --- 5 new tests for the hybrid matcher ---

def _gt(
    file: str = "a.js",
    lines: str = "10-20",
    must_mention: tuple[str, ...] = ("CRLF",),
    mandatory: bool = False,
    severity: str = "SERIOUS",
) -> dict[str, object]:
    return {
        "file": file,
        "lines": lines,
        "severity": severity,
        "must_mention": list(must_mention),
        "mandatory": mandatory,
        "issue_class": "injection",
    }


def _cand(
    file: str = "a.js",
    lines: str = "12-14",
    title: str = "CRLF header injection",
    severity: str = "SERIOUS",
) -> dict[str, object]:
    return {
        "file": file, "lines": lines, "title": title,
        "severity": severity, "issue_class": "other",
    }


def test_range_tol_is_five() -> None:
    assert RANGE_TOL == 5


def test_parse_ranges_caps_pathological_span_count() -> None:
    # the matcher shares hydra.line_spec.parse_line_spans (single source of truth)
    from hydra.line_spec import MAX_LINE_SPANS, parse_line_spans

    spec = ",".join(str(i) for i in range(1, 500))  # 499 comma-spans
    assert len(parse_line_spans(spec)) == MAX_LINE_SPANS  # bounded against adversarial mega-spec


def test_comma_separated_candidate_lines_match() -> None:
    # real reports cite multi-span lines like "15,21-22"; any sub-span must overlap the GT
    gt = [_gt(file="rate-limit.ts", lines="16-28", must_mention=("done", "async"))]
    cand = [_cand(file="rate-limit.ts", lines="15,21-22", title="async onRequest declares done")]
    assert score_case(gt, cand, judge=None).matched == 1


def test_keyword_match_required_when_must_mention_present() -> None:
    # file+range overlap but NO keyword -> miss (judge disabled)
    score = score_case([_gt()], [_cand(title="something unrelated")], judge=None)
    assert score.matched == 0


def test_keyword_match_hits() -> None:
    score = score_case([_gt()], [_cand(title="CRLF injection in headers")], judge=None)
    assert score.matched == 1
    assert score.recall == 1.0


def test_judge_only_called_on_prefilter_pass_keyword_fail() -> None:
    calls: list[tuple[str, str]] = []

    def judge(gt: dict[str, object], cand: dict[str, object]) -> bool:
        calls.append((str(gt["file"]), str(cand["file"])))
        return True

    # keyword fails but file+range pass -> judge consulted -> match
    score = score_case([_gt()], [_cand(title="totally different wording")], judge=judge)
    assert score.matched == 1
    assert len(calls) == 1  # judge invoked exactly once


def test_judge_not_called_when_range_fails() -> None:
    calls: list[int] = []

    def judge(gt: dict[str, object], cand: dict[str, object]) -> bool:
        calls.append(1)
        return True

    score = score_case([_gt(lines="10-20")], [_cand(lines="100-110", title="x")], judge=judge)
    assert score.matched == 0
    assert calls == []  # pre-filter rejected before judge


# --- optimal matching: overlapping GT ranges must not misattribute recall (Tier-2) ---

def test_overlapping_gt_uses_optimal_matching_not_greedy() -> None:
    # Two GT findings on overlapping ranges. Candidate X satisfies BOTH; candidate Y
    # satisfies ONLY A. Greedy (GT order, first free candidate) lets A grab X, leaving B
    # with only Y -> B missed (recall 0.5). Optimal matching assigns A<-Y, B<-X -> both
    # matched (recall 1.0). cases 01/05/07/08 have such overlapping intra-case ranges.
    gt = [
        _gt(file="a.js", lines="10-20", must_mention=("alpha",)),
        _gt(file="a.js", lines="10-20", must_mention=("beta",)),
    ]
    cands = [
        _cand(file="a.js", lines="10-12", title="alpha and beta both here"),  # matches A & B
        _cand(file="a.js", lines="10-12", title="alpha only here"),           # matches A only
    ]
    score = score_case(gt, cands, judge=None)
    assert score.matched == 2
    assert score.recall == 1.0


# --- false_positive_rate: explicit distractor-resistance metric (Track-3 P2) ---

def test_no_negative_anchors_means_zero_fp_rate() -> None:
    score = score_case([_gt()], [_cand()])
    assert score.false_positives == 0
    assert score.false_positive_rate == 0.0


def test_candidate_overlapping_negative_anchor_is_a_false_positive() -> None:
    # GT at 10-20; a benign distractor lives at 40-42; a candidate flagging it = explicit FP
    gt = [_gt(file="a.js", lines="10-20")]
    cands = [
        _cand(file="a.js", lines="12-14", title="CRLF header injection"),  # real match
        _cand(file="a.js", lines="40-41", title="suspicious eval call"),    # FP on distractor
    ]
    neg = [{"file": "a.js", "lines": "40-42", "why_benign": "guarded eval behind a constant"}]
    score = score_case(gt, cands, negative_anchors=neg)
    assert score.matched == 1
    assert score.false_positives == 1
    assert score.false_positive_rate == 0.5  # 1 FP / 2 candidates


def test_matched_candidate_is_not_counted_as_false_positive() -> None:
    # a candidate that matched a GT must never be double-counted as an FP, even if a
    # negative anchor sits within range tolerance of the GT
    gt = [_gt(file="a.js", lines="10-20", must_mention=("CRLF",))]
    cands = [_cand(file="a.js", lines="12-14", title="CRLF header injection")]
    neg = [{"file": "a.js", "lines": "12-12", "why_benign": "benign-but-near"}]
    score = score_case(gt, cands, negative_anchors=neg)
    assert score.matched == 1
    assert score.false_positives == 0


def test_negative_anchor_in_other_file_is_not_a_false_positive() -> None:
    gt = [_gt(file="a.js", lines="10-20")]
    cands = [_cand(file="b.js", lines="40-41", title="noise elsewhere")]
    neg = [{"file": "a.js", "lines": "40-42", "why_benign": "benign in a.js only"}]
    score = score_case(gt, cands, negative_anchors=neg)
    assert score.false_positives == 0
    assert score.false_positive_rate == 0.0
