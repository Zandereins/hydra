from bench.runner.report import RegressionResult, check_regression


def _baseline(
    cr_by_case: dict[str, float], f1_by_case: dict[str, float] | None = None
) -> dict[str, object]:
    cases: dict[str, object] = {}
    for c, cr in cr_by_case.items():
        entry: dict[str, float] = {"median_critical_recall": cr}
        if f1_by_case is not None:
            entry["median_f1"] = f1_by_case[c]
        cases[c] = entry
    return {"cases": cases}


def test_no_regression_when_stable() -> None:
    base = _baseline({"c1": 1.0, "c2": 1.0, "c3": 1.0, "c4": 1.0, "c5": 1.0})
    current = {"c1": 1.0, "c2": 1.0, "c3": 1.0, "c4": 1.0, "c5": 1.0}
    res = check_regression(base, current)
    assert isinstance(res, RegressionResult)
    assert res.failed is False


def test_regression_when_two_cases_lose_mandatory_finding() -> None:
    base = _baseline({"c1": 1.0, "c2": 1.0, "c3": 1.0, "c4": 1.0, "c5": 1.0})
    current = {"c1": 0.0, "c2": 0.0, "c3": 1.0, "c4": 1.0, "c5": 1.0}  # c1,c2 lost (−100pp)
    res = check_regression(base, current)
    assert res.failed is True
    assert set(res.regressed_cases) == {"c1", "c2"}


def test_single_case_loss_is_not_release_fail_but_warns() -> None:
    base = _baseline({"c1": 1.0, "c2": 1.0, "c3": 1.0, "c4": 1.0, "c5": 1.0})
    current = {"c1": 0.0, "c2": 1.0, "c3": 1.0, "c4": 1.0, "c5": 1.0}
    res = check_regression(base, current)
    assert res.failed is False  # only 1 of 5 lost
    assert res.warned_cases == ["c1"]  # −100pp > 15pp -> soft-warn


def test_missing_case_treated_as_zero() -> None:
    base = _baseline({"c1": 1.0, "c2": 1.0, "c3": 1.0, "c4": 1.0, "c5": 1.0})
    current = {"c1": 1.0, "c2": 1.0, "c3": 1.0, "c4": 1.0}  # c5 vanished
    res = check_regression(base, current)
    assert res.deltas["c5"] == -1.0  # absent case = full drop
    assert "c5" in res.warned_cases


def test_f1_is_diagnostic_only_never_gates() -> None:
    # F1 collapses but critical_recall holds -> NOT a regression (F1 is not gated)
    base = _baseline(
        {"c1": 1.0, "c2": 1.0, "c3": 1.0, "c4": 1.0, "c5": 1.0},
        {"c1": 0.5, "c2": 0.5, "c3": 0.5, "c4": 0.5, "c5": 0.5},
    )
    res = check_regression(
        base,
        {"c1": 1.0, "c2": 1.0, "c3": 1.0, "c4": 1.0, "c5": 1.0},
        current_f1={"c1": 0.2, "c2": 0.2, "c3": 0.5, "c4": 0.5, "c5": 0.5},
    )
    assert res.failed is False  # critical_recall stable -> no gate trip
    assert res.f1_deltas["c1"] == -0.3  # F1 drop is reported, not gated
