import json
from pathlib import Path

from bench.runner.models import GroundTruthFinding

CASES_DIR = Path(__file__).resolve().parents[2] / "bench" / "cases"


def test_every_case_ground_truth_validates_and_has_keywords() -> None:
    case_dirs = sorted(p for p in CASES_DIR.iterdir() if p.is_dir())
    assert len(case_dirs) == 5
    for case in case_dirs:
        lines = (case / "expected_findings.jsonl").read_text().splitlines()
        rows = [json.loads(line) for line in lines if line.strip()]
        assert rows, f"{case.name} has no ground-truth findings"
        for row in rows:
            gt = GroundTruthFinding.model_validate(row)  # raises if must_mention missing/empty
            assert gt.must_mention
