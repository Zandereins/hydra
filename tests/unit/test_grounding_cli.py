import json
from pathlib import Path

import pytest

from hydra.__main__ import main


def _write_findings(path: Path) -> None:
    findings = [{
        "id": "f1", "title": "CRLF injection setHeader", "severity": "SERIOUS",
        "evidence": "VERIFIED", "position": "CONCERN",
        "file": "app.js", "lines": "1-1",
        "chain": {"premise": "setHeader CRLF", "execution_trace": "", "conclusion": "injection"},
    }]
    path.write_text("\n".join(json.dumps(f) for f in findings))


def test_ground_cli_writes_grounded_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "app.js").write_text("setHeader CRLF injection here\n")
    findings_path = tmp_path / "findings.jsonl"
    out_path = tmp_path / "grounded.jsonl"
    _write_findings(findings_path)

    rc = main([
        "ground",
        "--findings", str(findings_path),
        "--repo", str(tmp_path),
        "--out", str(out_path),
    ])

    assert rc == 0
    captured = capsys.readouterr()
    assert "## Grounding Summary" in captured.out
    grounded = [json.loads(line) for line in out_path.read_text().splitlines() if line.strip()]
    assert grounded[0]["grounding"] == "CITATION_PRESENT"


def test_ground_cli_path_escape_nonzero_when_strict(tmp_path: Path) -> None:
    findings_path = tmp_path / "f.jsonl"
    findings_path.write_text(json.dumps({
        "id": "x", "title": "t", "severity": "SERIOUS", "evidence": "VERIFIED",
        "position": "CONCERN", "file": "../../etc/passwd", "lines": "1-1",
        "chain": {"premise": "p", "execution_trace": "", "conclusion": "c"},
    }))
    rc = main(["ground", "--findings", str(findings_path), "--repo", str(tmp_path), "--strict"])
    assert rc == 1  # --strict: a PATH_ESCAPE makes the run fail loudly
