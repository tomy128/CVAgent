from resume_agent.output import write_failure_artifacts


def test_failure_artifacts_label_draft_as_unsafe(tmp_path) -> None:
    state = {
        "requirements": [],
        "evidence_map": {"matches": []},
        "evidence_chunks": [],
        "retrieval_history": [],
        "retrieval_attempt": 1,
        "draft": {"resume_markdown": "Invented scale", "claims": []},
        "verification": {
            "corrected_resume_markdown": "Invented scale",
            "supported_claims": [],
            "unsupported_claims": [
                {"claim": "Invented scale", "reason": "No evidence"}
            ],
        },
    }
    issues = [{"claim": "Invented scale", "reason": "No evidence"}]

    write_failure_artifacts(tmp_path, state, issues)

    assert not (tmp_path / "tailored-resume.md").exists()
    assert (tmp_path / "unsafe-draft.md").read_text() == "Invented scale"
    report = (tmp_path / "failure-report.md").read_text()
    assert "Invented scale" in report
    assert "cannot be approved" in report
