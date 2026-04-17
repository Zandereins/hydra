import pytest
from pathlib import Path

@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    (tmp_path / ".hydra").mkdir()
    return tmp_path

@pytest.fixture
def run_nonce() -> str:
    return "abc123"
