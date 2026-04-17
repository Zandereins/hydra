from hydra.phase1.seed_ids import SeedIdAssigner, assign_seed_id


def test_assign_preserves_source_prefix() -> None:
    a = SeedIdAssigner()
    assert a.next("semgrep") == "T-SEM-1"
    assert a.next("semgrep") == "T-SEM-2"
    assert a.next("osv") == "T-OSV-1"
    assert a.next("lang_checker") == "T-LANG-1"
    assert a.next("echo") == "E-1"
    assert a.next("navigator") == "N-1"


def test_unknown_source_raises() -> None:
    a = SeedIdAssigner()
    import pytest
    with pytest.raises(ValueError):
        a.next("made_up")


def test_assign_seed_id_standalone() -> None:
    assert assign_seed_id("semgrep", 1) == "T-SEM-1"
    assert assign_seed_id("osv", 42) == "T-OSV-42"


def test_assign_seed_id_unknown_source_raises() -> None:
    import pytest
    with pytest.raises(ValueError):
        assign_seed_id("made_up", 1)
