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
    return {"file": file, "lines": lines, "title": title, "severity": severity, "issue_class": "other"}


def test_range_tol_is_five() -> None:
    assert RANGE_TOL == 5


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
