import json
from pathlib import Path

from resume_agent.cli import main


def test_demo_cli_writes_expected_artifacts(tmp_path: Path) -> None:
    jd = tmp_path / "jd.md"
    resume = tmp_path / "resume.md"
    evidence = tmp_path / "evidence"
    output = tmp_path / "output"
    evidence.mkdir()
    jd.write_text("# JD\n\n- Python\n- LangGraph workflow", encoding="utf-8")
    resume.write_text("# Resume\n\nPython backend engineer", encoding="utf-8")
    (evidence / "project.md").write_text("Built a LangGraph workflow", encoding="utf-8")

    exit_code = main(
        [
            "tailor",
            "--jd",
            str(jd),
            "--resume",
            str(resume),
            "--evidence",
            str(evidence),
            "--output",
            str(output),
            "--demo",
            "--yes",
        ]
    )

    assert exit_code == 0
    run_dir = next(output.iterdir())
    assert (run_dir / "tailored-resume.md").read_text(encoding="utf-8") == resume.read_text(encoding="utf-8")
    assert json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["status"] == "approved"
