from bench.runner.run_bench import FAST_BENCH_CASES, discover_cases, plan_runs


def test_discover_cases_finds_all_five():
    cases = discover_cases()
    assert len(cases) == 5
    assert "01-axios-header-injection" in cases


def test_fast_bench_is_two_cases_one_run():
    runs = plan_runs(mode="fast")
    assert sorted({r.case_id for r in runs}) == sorted(FAST_BENCH_CASES)
    assert all(r.runs == 1 and r.hydra_mode == "standard" for r in runs)


def test_full_bench_is_five_cases_standard_and_deep_three_runs():
    runs = plan_runs(mode="full")
    assert len({r.case_id for r in runs}) == 5
    modes = {(r.case_id, r.hydra_mode) for r in runs}
    assert len(modes) == 10  # 5 cases x {standard, deep}
    assert all(r.runs == 3 for r in runs)
