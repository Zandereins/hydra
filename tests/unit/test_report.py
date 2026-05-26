from bench.runner.report import RegressionResult, check_regression


def _baseline(f1_by_case: dict[str, float]) -> dict[str, object]:
    return {"cases": {c: {"median_f1": v} for c, v in f1_by_case.items()}}


def test_no_regression_when_stable() -> None:
    base = _baseline({"c1": 0.8, "c2": 0.7, "c3": 0.9, "c4": 0.6, "c5": 0.75})
    current = {"c1": 0.8, "c2": 0.71, "c3": 0.88, "c4": 0.6, "c5": 0.75}
    res = check_regression(base, current)
    assert isinstance(res, RegressionResult)
    assert res.failed is False


def test_regression_when_two_cases_drop_10pp() -> None:
    base = _baseline({"c1": 0.8, "c2": 0.7, "c3": 0.9, "c4": 0.6, "c5": 0.75})
    current = {"c1": 0.69, "c2": 0.59, "c3": 0.9, "c4": 0.6, "c5": 0.75}  # c1,c2 drop >=10pp
    res = check_regression(base, current)
    assert res.failed is True
    assert set(res.regressed_cases) == {"c1", "c2"}


def test_single_case_drop_is_not_release_fail() -> None:
    base = _baseline({"c1": 0.8, "c2": 0.7, "c3": 0.9, "c4": 0.6, "c5": 0.75})
    current = {"c1": 0.5, "c2": 0.7, "c3": 0.9, "c4": 0.6, "c5": 0.75}
    res = check_regression(base, current)
    assert res.failed is False  # only 1 of 5 dropped
