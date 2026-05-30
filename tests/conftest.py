from pathlib import Path

import pytest


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    (tmp_path / ".hydra").mkdir()
    return tmp_path


@pytest.fixture
def run_nonce() -> str:
    return "abc123def456"  # 12 hex = 48-bit, matches the widened nonce contract
